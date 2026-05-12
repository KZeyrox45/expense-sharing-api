# Celery tasks for email notifications.
#
# Architecture:
#   Celery task (sync) -> asyncio.run() -> _async_* helper (async) -> DB + FastMail
#
# All task arguments are plain strings (UUIDs as str) because Celery
# serializes arguments as JSON, which does not support UUID objects.

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal

from celery import Task
from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# --- Mail client - created once at module level ----------------------------------
# FastMail is stateless (just holds config), safe to reuse across tasks.
_mail_conf = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_USERNAME,
    MAIL_PASSWORD=settings.MAIL_PASSWORD,
    MAIL_FROM=settings.MAIL_FROM,
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SERVER=settings.MAIL_SERVER,
    MAIL_STARTTLS=settings.MAIL_STARTTLS,
    MAIL_SSL_TLS=settings.MAIL_SSL_TLS,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True
)
_mail = FastMail(_mail_conf)


# --- Task DB session -------------------------------------------------------------

@asynccontextmanager
async def _task_db():
    """
    Yield a fresh AsyncSession using NullPool for Celery tasks.

    WHY NullPool:
    Celery prefork workers run tasks in forked subprocesses. asyncio.run()
    creates a NEW event loop per task, but a module-level engine holds connections
    bound to the ORIGINAL loop from the parent process -> RuntimeError.

    NullPool creates a new connection per request and closes it immediately,
    so there is never a stale connection from a different event loop.

    This is the standard pattern for asyncpg + Celery prefork.
    """
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    TaskSession = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    try:
        async with TaskSession() as session:
            yield session
    finally:
        # Always dispose the engine to release the connection cleanly
        await engine.dispose()


# --- Shared email helper ---------------------------------------------------------

async def _send_email(to: str, subject: str, html: str) -> None:
    """Send a single HTML email. Raises on failure - callers handle per-recipient."""
    message = MessageSchema(
        subject=subject,
        recipients=[to],
        body=html,
        subtype=MessageType.html
    )
    await _mail.send_message(message)


# --- Task 1: Expense notification ------------------------------------------------

@celery_app.task(
    name="app.tasks.email_tasks.send_expense_notification",
    bind=True,
    max_retries=3,
    default_retry_delay=60      # Retry after 60 seconds on failure
)
def send_expense_notification(
    self: Task,
    expense_id: str,
    group_id: str,
    # expense.creator is loaded from DB directly.
) -> None:
    """Notify all group members when a new expense is added."""
    try:
        asyncio.run(_async_send_expense_notification(
            uuid.UUID(expense_id),
            uuid.UUID(group_id)
        ))
    except Exception as exc:
        logger.error(f"send_expense_notification failed for expense {expense_id}: {exc}")
        # Retry with exponential backoff
        raise self.retry(exc=exc)


async def _async_send_expense_notification(
    expense_id: uuid.UUID,
    group_id: uuid.UUID
) -> None:
    from app.db.models.expense import Expense, ExpenseSplit
    from app.db.models.group import Group, GroupMember

    async with _task_db() as db:
        # Load expense with all relationships needed for the email
        expense_result = await db.execute(
            select(Expense)
            .where(Expense.id == expense_id)
            .options(
                selectinload(Expense.splits).selectinload(ExpenseSplit.user),
                selectinload(Expense.creator),
            )
        )
        expense = expense_result.scalar_one_or_none()
        if expense is None:
            logger.warning(f"Expense {expense_id} not found, skipping notification")
            return

        # Load group with members and their user info
        group_result = await db.execute(
            select(Group)
            .where(Group.id == group_id)
            .options(selectinload(Group.members).selectinload(GroupMember.user))
        )
        group = group_result.scalar_one_or_none()
        if group is None:
            return

        # Build split lookup: user_id -> amount owed
        split_map: dict[uuid.UUID, Decimal] = {
            s.user_id: s.amount for s in expense.splits
        }

        # Send individual email to each member
        for member in group.members:
            user_split = split_map.get(member.user_id)
            split_line = (
                f"<li>Your share: <strong>{user_split:.2f}</strong></li>"
                if user_split is not None
                else "<li>You are not included in the split for this expense.</li>"
            )

            html = f"""
            <h2>New Expense in <em>{group.name}</em></h2>
            <p>
              <strong>{expense.creator.username}</strong> added a new expense:
            </p>
            <ul>
              <li>Description: <strong>{expense.description}</strong></li>
              <li>Total: <strong>{expense.total_amount:.2f}</strong></li>
              <li>Split type: {expense.split_type.value}</li>
              {split_line}
            </ul>
            <p>Check the app to view the full breakdown and current balances.</p>
            """

            try:
                await _send_email(
                    to=member.user.email,
                    subject=f"[{group.name}] New expense: {expense.description}",
                    html=html,
                )
                logger.info(f"Expense notification sent to {member.user.email}")
            except Exception as exc:
                # Log per-recipient failure and continue - don't block other recipients
                logger.error(
                    f"Failed to send expense notification to {member.user.email}: {exc}"
                )


# --- Task 2: Settlement notification ---------------------------------------------

@celery_app.task(
    name="app.tasks.email_tasks.send_settlement_notification",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def send_settlement_notification(self: Task, settlement_id: str) -> None:
    """Notify the receiver when someone pays them."""
    try:
        asyncio.run(_async_send_settlement_notification(uuid.UUID(settlement_id)))
    except Exception as exc:
        logger.error(f"send_settlement_notification failed for {settlement_id}: {exc}")
        raise self.retry(exc=exc)


async def _async_send_settlement_notification(settlement_id: uuid.UUID) -> None:
    from app.db.models.group import Group
    from app.db.models.settlement import Settlement

    async with _task_db() as db:
        result = await db.execute(
            select(Settlement)
            .where(Settlement.id == settlement_id)
            .options(
                selectinload(Settlement.payer),
                selectinload(Settlement.receiver),
            )
        )
        settlement = result.scalar_one_or_none()
        if settlement is None:
            logger.warning(f"Settlement {settlement_id} not found, skipping notification")
            return

        group_result = await db.execute(
            select(Group).where(Group.id == settlement.group_id)
        )
        group = group_result.scalar_one_or_none()
        group_name = group.name if group else "your group"

        note_line = f"<p>Note: {settlement.note}</p>" if settlement.note else ""

        html = f"""
        <h2>Payment Received</h2>
        <p>
          <strong>{settlement.payer.username}</strong> paid you
          <strong>{settlement.amount:.2f}</strong> in <em>{group_name}</em>.
        </p>
        {note_line}
        <p>Check the app to see your updated balance.</p>
        """

        try:
            await _send_email(
                to=settlement.receiver.email,
                subject=f"[{group_name}] {settlement.payer.username} paid you {settlement.amount:.2f}",
                html=html,
            )
            logger.info(f"Settlement notification sent to {settlement.receiver.email}")
        except Exception as exc:
            logger.error(
                f"Failed to send settlement notification to {settlement.receiver.email}: {exc}"
            )


# --- Task 3: Weekly balance summary (Celery Beat) -------------------------------------

@celery_app.task(name="app.tasks.email_tasks.send_weekly_summary")
def send_weekly_summary() -> None:
    """Scheduled task - runs every Monday 08:00 UTC via Celery Beat."""
    logger.info("Starting weekly balance summary task")
    asyncio.run(_async_send_weekly_summary())
    logger.info("Weekly balance summary task complete")


async def _async_send_weekly_summary() -> None:
    from app.db.models.expense import Expense
    from app.db.models.group import Group, GroupMember
    from app.db.models.settlement import Settlement
    from app.services.balance_service import _calculate_net_balances, _simplify_debts

    async with _task_db() as db:
        # Load all groups with members
        groups_result = await db.execute(
            select(Group).options(
                selectinload(Group.members).selectinload(GroupMember.user)
            )
        )
        groups = groups_result.scalars().all()

        for group in groups:
            if not group.members:
                continue

            member_ids = {m.user_id for m in group.members}
            user_map = {m.user_id: m.user for m in group.members}

            # Load expenses for this group
            expenses_result = await db.execute(
                select(Expense)
                .where(
                    Expense.group_id == group.id,
                    Expense.is_deleted.is_(False),
                )
                .options(
                    selectinload(Expense.payers),
                    selectinload(Expense.splits),
                )
            )
            expenses = expenses_result.scalars().all()

            # Load settlements for this group
            settlements_result = await db.execute(
                select(Settlement).where(Settlement.group_id == group.id)
            )
            settlements = settlements_result.scalars().all()

            # Reuse pure functions from balance_service
            net = _calculate_net_balances(expenses, settlements, member_ids)
            simplified_debts = _simplify_debts(net)

            # Send personalized summary to each member
            for member in group.members:
                user_net = net.get(member.user_id, Decimal("0"))

                # Debts relevant to this member only
                user_debts = [
                    (debtor_id, creditor_id, amount)
                    for debtor_id, creditor_id, amount in simplified_debts
                    if debtor_id == member.user_id or creditor_id == member.user_id
                ]

                # Skip fully-settled members - no noise
                if abs(user_net) < Decimal("0.01") and not user_debts:
                    continue

                html = _build_weekly_summary_html(
                    group.name,
                    member.user.username,
                    user_net,
                    user_debts,
                    user_map,
                )

                try:
                    await _send_email(
                        to=member.user.email,
                        subject=f"[Weekly Summary] {group.name}",
                        html=html,
                    )
                    logger.info(f"Weekly summary sent to {member.user.email}")
                except Exception as exc:
                    logger.error(
                        f"Failed to send weekly summary to {member.user.email}: {exc}"
                    )


def _build_weekly_summary_html(
    group_name: str,
    username: str,
    net_amount: Decimal,
    user_debts: list[tuple],
    user_map: dict,
) -> str:
    """Build HTML body for the weekly summary email."""
    if net_amount > Decimal("0.01"):
        balance_line = f"You are owed <strong style='color:green'>{net_amount:.2f}</strong>"
    elif net_amount < Decimal("-0.01"):
        balance_line = f"You owe <strong style='color:red'>{abs(net_amount):.2f}</strong>"
    else:
        balance_line = "You are <strong>fully settled</strong>"

    if user_debts:
        items = "".join(
            f"<li>{user_map[d].username} → {user_map[c].username}: <strong>{a:.2f}</strong></li>"
            for d, c, a in user_debts
        )
        debts_section = f"<h3>Pending Transactions</h3><ul>{items}</ul>"
    else:
        debts_section = "<p>No pending transactions - all settled!</p>"

    return f"""
    <h2>Weekly Summary - <em>{group_name}</em></h2>
    <p>Hi <strong>{username}</strong>, here is your balance update:</p>
    <p>{balance_line}</p>
    {debts_section}
    <hr>
    <small>You receive this email every Monday. Log in to settle your balances.</small>
    """