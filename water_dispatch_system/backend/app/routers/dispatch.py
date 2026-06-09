from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import DispatchCommand
from app.schemas import DispatchRequest, DispatchCommandOut, DispatchPlanOut, WaterBalanceOut
from app.services.dispatch_service import calculate_dispatch_plan, execute_dispatch_plan

router = APIRouter(tags=["dispatch"])


@router.post("/plan", response_model=DispatchPlanOut)
async def create_dispatch_plan(
    request: DispatchRequest, db: AsyncSession = Depends(get_db)
):
    plan = await calculate_dispatch_plan(
        request.canal_id, request.downstream_demand, db
    )
    saved_commands = await execute_dispatch_plan(plan)

    command_outs = [
        DispatchCommandOut(
            id=c.id,
            plan_id=c.plan_id,
            target_type=c.target_type,
            target_id=c.target_id,
            target_name=c.target_name,
            command_type=c.command_type,
            command_value=c.command_value,
            mqtt_topic=c.mqtt_topic,
            status=c.status,
            created_at=c.created_at,
            sent_at=c.sent_at,
            acked_at=c.acked_at,
        )
        for c in saved_commands
    ]

    wb = plan.get("water_balance", {})
    water_balance = WaterBalanceOut(
        canal_id=wb.get("canal_id", request.canal_id),
        canal_name=wb.get("canal_name", ""),
        total_inflow=wb.get("total_inflow", 0),
        total_outflow=wb.get("total_outflow", 0),
        total_storage_change=wb.get("total_storage_change", 0),
        total_loss=wb.get("total_loss", 0),
        balance_error=wb.get("balance_error", 0),
        balance_error_percent=wb.get("balance_error_percent", 0.0),
    )

    return DispatchPlanOut(
        plan_id=plan["plan_id"],
        canal_id=request.canal_id,
        commands=command_outs,
        water_balance=water_balance,
    )


@router.get("/commands", response_model=list[DispatchCommandOut])
async def list_commands(
    status: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    since = datetime.utcnow() - timedelta(hours=24)
    stmt = (
        select(DispatchCommand)
        .where(DispatchCommand.created_at >= since)
        .order_by(desc(DispatchCommand.created_at))
    )
    if status:
        stmt = stmt.where(DispatchCommand.status == status)

    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [DispatchCommandOut.model_validate(r) for r in rows]


@router.get("/commands/{command_id}", response_model=DispatchCommandOut)
async def get_command(command_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(DispatchCommand).where(DispatchCommand.id == command_id)
    result = await db.execute(stmt)
    cmd = result.scalar_one_or_none()
    if not cmd:
        raise HTTPException(status_code=404, detail="Command not found")
    return DispatchCommandOut.model_validate(cmd)


@router.post("/commands/{command_id}/cancel", response_model=DispatchCommandOut)
async def cancel_command(command_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(DispatchCommand).where(DispatchCommand.id == command_id)
    result = await db.execute(stmt)
    cmd = result.scalar_one_or_none()
    if not cmd:
        raise HTTPException(status_code=404, detail="Command not found")
    if cmd.status != "pending":
        raise HTTPException(status_code=400, detail="Only pending commands can be cancelled")

    cmd.status = "cancelled"
    await db.commit()
    await db.refresh(cmd)
    return DispatchCommandOut.model_validate(cmd)


@router.get("/history", response_model=list[DispatchCommandOut])
async def dispatch_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * page_size
    stmt = (
        select(DispatchCommand)
        .order_by(desc(DispatchCommand.created_at))
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [DispatchCommandOut.model_validate(r) for r in rows]
