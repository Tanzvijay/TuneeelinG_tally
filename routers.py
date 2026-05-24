from fastapi import APIRouter

from repo import (
    fetch_Outstanding_data,
    list_database_tables_agent,
    get_table_data,
    fetch_monthly_provision_data
)

router = APIRouter()


@router.get("/tables/")
def list_tables():

    return list_database_tables_agent()


# PostgreSQL tables only
@router.get("/tables/{table_name}/data/")
def get_table_data_endpoint(
    table_name: str,
    limit: int = 100
):

    return get_table_data(
        table_name,
        limit
    )


# Tally XML endpoint
@router.get("/monthly_provision/")
def monthly_provision_endpoint(
    ledger_name: str,
    from_date: str,
    to_date: str,
    period: str
):

    data = fetch_monthly_provision_data(
        ledger_name,
        from_date,
        to_date,
        period
    )

    return {
        "status": "success",
        "count": len(data),
        "data": data
    }


@router.get("/outstanding_report_data/")
def outstanding_report_data_endpoint(
    ledger_name: str,
    from_date: str,
    to_date: str,
   
):

    data = fetch_Outstanding_data(
        ledger_name,
        from_date,
        to_date,
  
    )

    return {
        "status": "success",
        "count": len(data),
        "data": data
    }