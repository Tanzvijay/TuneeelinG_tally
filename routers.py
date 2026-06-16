from fastapi import APIRouter
from fastapi import Depends
from repo import (
    Balance_Sheet_Report,
    Cost_Center_Summary_Report,
    Godown_Summary_Report,
    Movenment_analaysis,
    Statistics_Report,
    Stock_Group_Summary,
    Stock_analzer,
    fetch_Outstanding_data,
    fetch_monthly_provision_data,
    get_table_data,
    list_database_tables_agent,
    multi_transaction,
    profit_and_loss_report,
    Stock_Category_Summary,
    Ratio_Analysis,
    Negative_Ledgers_Report,
    Order_Outstandings_Report,
    Overdue_Payables_Report,
    Trial_Balance_Report,
    Stock_Purchase_Report,
    verify_api_key
   

    
    
)

router = APIRouter()


@router.get("/tables")
def list_tables(api_key: str = Depends(verify_api_key)):
    return list_database_tables_agent()


@router.get("/tables/{table_name}/data")
def get_table_data_endpoint(table_name: str, limit: int = 100,api_key: str = Depends(verify_api_key)):
    return get_table_data(table_name=table_name, limit=limit)


@router.get("/Ledeger_Transaction")
def monthly_provision_endpoint(
    ledger_name: str,
    from_date: str,
    to_date: str,
    period: str,
    file_name: str = None,

):
    data = fetch_monthly_provision_data(
        ledger_name=ledger_name,
        from_date=from_date,
        to_date=to_date,
        period=period,
        file_name=file_name
    )
    return {"status": "success", "count": len(data), "data": data}


@router.get("/Ledger_outstanding-report")
def outstanding_report_endpoint(
    ledger_name: str,
    from_date: str,
    to_date: str,
    file_name: str = None
):
    
    data = fetch_Outstanding_data(
        ledger_name=ledger_name,
        from_date=from_date,
        to_date=to_date,
        file_name=file_name
    )
    return {"status": "success", "count": len(data), "data": data}


@router.get("/multi-transaction")
def multi_transaction_endpoint(
    report_name: str,
    from_date: str,
    to_date: str,
    period: str,
    file_name: str = None,
):
    data = multi_transaction(
        report_name=report_name,
        from_date=from_date,
        to_date=to_date,
        period=period,
        file_name=file_name
    )
    return {"status": "success", "count": len(data), "data": data}


@router.get("/profit-and-loss")
def profit_and_loss_endpoint(from_date: str, to_date: str, file_name: str = None):
    data = profit_and_loss_report(from_date=from_date, to_date=to_date, file_name=file_name)
    return {"status": "success", "count": len(data), "data": data}


@router.get("/stock-analysis")
def stock_analysis_endpoint(
    from_date: str,
    to_date: str,
    StockItemName: str,
    file_name: str = None,
):
    data = Stock_analzer(
        date_from=from_date,
        date_to=to_date,
        StockItemName=StockItemName,
        file_name=file_name
    )
    return {"status": "success", "count": len(data), "data": data}


@router.get("/stock-group-summary")
def stock_group_summary_endpoint(from_date: str, to_date: str,file_name: str = None):
    data = Stock_Group_Summary(from_date=from_date, to_date=to_date,file_name=file_name)
    return {"status": "success", "count": len(data), "data": data}


@router.get("/movement-analysis")
def movement_analysis_endpoint(from_date: str, to_date: str,file_name: str = None):
    data = Movenment_analaysis(from_date=from_date, to_date=to_date,file_name=file_name)
    
    return {"status": "success", "count": len(data), "data": data}


@router.get("/stock-category-summary")
def stock_category_summary_endpoint(
    from_date: str,
    to_date: str,
    file_name: str = None,
):
    data = Stock_Category_Summary(
        from_date=from_date,
        to_date=to_date,
        file_name=file_name
    )

    if isinstance(data, list):
        return {
            "status": "success",
            "count": len(data),
            "data": data
        }

    return {
        "status": "success",
        "data": data
        
    }



@router.get("/ratio-analysis")
def ratio_analysis_endpoint(
    from_date: str,
    to_date: str,
    file_name: str = None,
):
    data = Ratio_Analysis(
        from_date=from_date,
        to_date=to_date,
        file_name=file_name,
    )

    if isinstance(data, list):
        return {
            "status": "success",
            "count": len(data),
            "data": data,
        }

    return {
        "status": "success",
        "data": data,
    }

@router.get("/negative-ledgers")
def negative_ledgers_endpoint(
    from_date: str,
    to_date: str,
    file_name: str = None,
):
    data = Negative_Ledgers_Report(
        from_date=from_date,
        to_date=to_date,
        file_name=file_name
    )

    if isinstance(data, list):
        return {
            "status": "success",
            "count": len(data),
            "data": data
        }

    return {
        "status": "success",
        "data": data
    }



@router.get("/order-outstandings")
def order_outstandings_endpoint(
    from_date: str,
    to_date: str,
    file_name: str = None,
):
    data = Order_Outstandings_Report(
        from_date=from_date,
        to_date=to_date,
        file_name=file_name
    )

    if isinstance(data, list):
        return {
            "status": "success",
            "count": len(data),
            "data": data
        }

    return {
        "status": "success",
        "data": data
    }


@router.get("/overdue-payables")
def overdue_payables_endpoint(
    from_date: str,
    to_date: str,
    file_name: str = None,
    ReportName: str = None
):
    data = Overdue_Payables_Report(
        from_date=from_date,
        to_date=to_date,
        file_name=file_name,
        ReportName=ReportName
    )

    if isinstance(data, list):
        return {
            "status": "success",
            "count": len(data),
            "data": data
        }

    return {
        "status": "success",
        "data": data
    }
@router.get("/trial-balance")
def trial_balance_endpoint(
    from_date: str,
    to_date: str,
    ledgerwise: str = "NO",
    file_name: str = None,
):

    data = Trial_Balance_Report(
        from_date=from_date,
        to_date=to_date,
        is_ledgerwise=ledgerwise,
        file_name=file_name
    )

    if isinstance(data, list):
        return {
            "status": "success",
            "count": len(data),
            "data": data
        }

    return {
        "status": "success",
        "data": data
    }



@router.get("/balance-sheet")
def balance_sheet_endpoint(
    from_date: str,
    to_date: str,
    file_name: str = None,
):

    data = Balance_Sheet_Report(
        from_date=from_date,
        to_date=to_date,
        file_name=file_name
    )

    if isinstance(data, list):
        return {
            "status": "success",
            "count": len(data),
            "data": data
        }

    return {
        "status": "success",
        "data": data
    }

@router.get("/cost-center-summary")
def cost_center_summary_endpoint(
    from_date: str,
    to_date: str,
    file_name: str = None,
):

    data = Cost_Center_Summary_Report(
        from_date=from_date,
        to_date=to_date,
        file_name=file_name
    )

    if isinstance(data, list):
        return {
            "status": "success",
            "count": len(data),
            "data": data
        }

    return {
        "status": "success",
        "data": data
    }
@router.get("/godown-summary")
def godown_summary_endpoint(
    from_date: str,
    to_date: str,
    file_name: str = None,
):

    data = Godown_Summary_Report(
        from_date=from_date,
        to_date=to_date,
        file_name=file_name
    )

    if isinstance(data, list):
        return {
            "status": "success",
            "count": len(data),
            "data": data
        }

    return {
        "status": "success",
        "data": data
    }



@router.get("/statistics")
def statistics_endpoint(
    from_date: str,
    to_date: str,
    file_name: str = None,
):

    data = Statistics_Report(
        from_date=from_date,
        to_date=to_date,
        file_name=file_name
    )

    if isinstance(data, list):
        return {
            "status": "success",
            "count": len(data),
            "data": data
        }

    return {
        "status": "success",
        "data": data
    }
@router.get("/stock-Query")
def stock_purchase_history(
    stock_item: str,
    from_date: str,
    to_date: str,
    file_name: str = None
):
    data = Stock_Purchase_Report(
        stock_item=stock_item,
        from_date=from_date,
        to_date=to_date,
        file_name=file_name
    )

    if isinstance(data, list):
        return {
            "status": "success",
            "count": len(data),
            "data": data
        }

    return {
        "status": "success",
        "data": data
    }

