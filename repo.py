import os
import re
import xml.etree.ElementTree as ET
import pandas as pd

import requests
from psycopg2 import sql
import calendar
from sqlalchemy import create_engine, text

import re

from fastapi import Header, HTTPException, Depends


API_KEY =os.getenv('API_KEY')


def verify_api_key(x_api_key: str = Header(None)):
    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid API Key"
        )
    return x_api_key



DATABASE_URL = (
    f"postgresql://{os.getenv('DB_USER')}:"
    f"{os.getenv('DB_PASSWORD')}@"
    f"{os.getenv('DB_HOST')}:"
    f"{os.getenv('DB_PORT')}/"
    f"{os.getenv('DB_NAME')}"
)
TALLY_URL=os.getenv('TALLY_URL')
engine = create_engine(DATABASE_URL)


def list_database_tables_agent():
    conn = engine.connect()

    try:
        result = conn.execute(
            text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name;
            """)
        )

        tables = [row[0] for row in result.fetchall()]

        return {
            "total_tables": len(tables),
            "tables": tables
        }

    finally:
        conn.close()




def get_table_data(table_name: str, limit: int = 100):
    with engine.connect() as conn:
        result = conn.execute(
            text(f'SELECT * FROM "{table_name}" LIMIT :limit'),
            {"limit": limit}
        )

        rows = result.fetchall()
        columns = result.keys()

        return {
            "table_name": table_name,
            "total_rows": len(rows),
            "columns": list(columns),
            "data": [dict(zip(columns, row)) for row in rows]
        }


def save_to_database(df: pd.DataFrame, table_name: str):
    if table_name!="":
        df.to_sql(
            table_name,
            engine,
            if_exists="replace",
            index=False
        )
        return {
            "total_records": len(df),
            "message": f"Successfully exported to database table: {table_name}"
        }
    else:
        return {

            "total_records": len(df),
            "message": "No table name provided. Data not saved to database."
        }
    






def fetch_monthly_provision_data(
    ledger_name,
    from_date,
    to_date,
    period,
    file_name=None
):

    xml_request = f"""
    <ENVELOPE>
        <HEADER>
            <TALLYREQUEST>Export Data</TALLYREQUEST>
        </HEADER>
        <BODY>
            <EXPORTDATA>
                <REQUESTDESC>
                    <REPORTNAME>Ledger Monthly Summary</REPORTNAME>
                    <STATICVARIABLES>
                        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
                        <SVFROMDATE>{from_date}</SVFROMDATE>
                        <SVTODATE>{to_date}</SVTODATE>
                        <LEDGERNAME>{ledger_name}</LEDGERNAME>
                        <SVPERIODICITY>{period}</SVPERIODICITY>
                    </STATICVARIABLES>
                </REQUESTDESC>
            </EXPORTDATA>
        </BODY>
    </ENVELOPE>
    """

    response = requests.post(
        TALLY_URL,
        data=xml_request,
        headers={"Content-Type": "application/xml"}
    )

    response.raise_for_status()

    root = ET.fromstring(response.text)

    rows = []
    children = list(root)

    for i in range(0, len(children), 2):

        try:

            if children[i].tag != "DSPPERIOD":
                continue

            rows.append(
                {
                    "Period": children[i].text.strip()
                    if children[i].text else "",

                    "DebitAmount": children[i + 1].findtext(
                        "./DSPDRAMT/DSPDRAMTA",
                        default=""
                    ),

                    "CreditAmount": children[i + 1].findtext(
                        "./DSPCRAMT/DSPCRAMTA",
                        default=""
                    ),

                    "ClosingAmount": children[i + 1].findtext(
                        "./DSPCLAMT/DSPCLAMTA",
                        default=""
                    )
                }
            )

        except Exception:
            continue

    df = pd.DataFrame(rows)
    cols = ["DebitAmount", "CreditAmount", "ClosingAmount"]
    fy_start = pd.to_datetime(from_date, format="%Y%m%d")
    

    df[["From Date", "To Date"]] = df["Period"].apply(lambda x: pd.Series(get_period_dates(x, fy_start)))

    date_cols = ["From Date", "To Date"]
    df[date_cols] = df[date_cols].apply(pd.to_datetime, errors="coerce")

    df[cols] = (
    df[cols]
    .apply(pd.to_numeric, errors="coerce")
    .fillna(0.0)
    .astype(float)

    
)


    return (
    save_to_database(df, file_name)
    if file_name
    else df.to_dict(orient="records")
)

def fetch_Outstanding_data(
    ledger_name,
    from_date,
    to_date,
    file_name=None
):

    xml_request = f"""
    <ENVELOPE>
        <HEADER>
            <TALLYREQUEST>Export Data</TALLYREQUEST>
        </HEADER>
        <BODY>
            <EXPORTDATA>
                <REQUESTDESC>
                    <REPORTNAME>Ledger Outstandings</REPORTNAME>
                    <STATICVARIABLES>
                        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
                        <SVFROMDATE>{from_date}</SVFROMDATE>
                        <SVTODATE>{to_date}</SVTODATE>
                        <LEDGERNAME>{ledger_name}</LEDGERNAME>
                    </STATICVARIABLES>
                </REQUESTDESC>
            </EXPORTDATA>
        </BODY>
    </ENVELOPE>
    """

    response = requests.post(
        TALLY_URL,
        data=xml_request,
        headers={"Content-Type": "application/xml"}
    )

  

    if not response.text.strip():
        return []

    try:
        root = ET.fromstring(response.text)

    except ET.ParseError:
        return []

    rows = []

    bill_fixed_list = root.findall(".//BILLFIXED")
    bill_ops = root.findall(".//BILLOP")
    bill_cls = root.findall(".//BILLCL")
    bill_dues = root.findall(".//BILLDUE")
    bill_overdues = root.findall(".//BILLOVERDUE")

    for i, bill in enumerate(bill_fixed_list):

        rows.append(
            {
                "Bill Date": bill.findtext("BILLDATE", ""),
                "Bill Ref": bill.findtext("BILLREF", ""),
                "Opening Amount": bill_ops[i].text if i < len(bill_ops) else "",
                "Closing Amount": bill_cls[i].text if i < len(bill_cls) else "",
                "Due Date": bill_dues[i].text if i < len(bill_dues) else "",
                "Overdue Days": bill_overdues[i].text if i < len(bill_overdues) else "",
            }
        )

    df = pd.DataFrame(rows)
    cols = ["Opening Amount", "Closing Amount", "Overdue Days"]
    date_cols = ["Bill Date", "Due Date"]
    df[date_cols] = df[date_cols].apply(pd.to_datetime, errors="coerce")

    

    df[cols] = (
        df[cols]
        .apply(pd.to_numeric, errors="coerce")
        .fillna(0.0)
        .astype(float)
    )

    return (
        save_to_database(df, file_name)
        if file_name
        else df.to_dict(orient="records")
    )


def normalize_period(period):
    period = str(period).strip()

    # Day: 1-Apr
    if re.match(r"^\d{1,2}-[A-Za-z]{3}$", period):
        return pd.to_datetime(period + "-2025", format="%d-%b-%Y")

    # Month: April
    if re.match(r"^[A-Za-z]+$", period):
        return pd.to_datetime(period + "-2025", format="%B-%Y")

    return period

def get_period_dates(period, financial_year_start):
    period = str(period).strip()

    # Month: April
    if re.match(r"^[A-Za-z]+$", period):
        dt = pd.to_datetime(
            f"{period}-{financial_year_start.year}",
            format="%B-%Y"
        )
        start_date = dt.replace(day=1)
        end_date = dt.replace(
            day=calendar.monthrange(dt.year, dt.month)[1]
        )
        return start_date.date(), end_date.date()

    # Day: 1-Apr
    if re.match(r"^\d{1,2}-[A-Za-z]{3}$", period):
        dt = pd.to_datetime(
            f"{period}-{financial_year_start.year}",
            format="%d-%b-%Y"
        )
        return dt.date(), dt.date()

    # Week: 3-Apr to 9-Apr
    if " to " in period and not re.search(r"\d{4}", period):
        start_str, end_str = period.split(" to ")

        start_dt = pd.to_datetime(
            f"{start_str}-{financial_year_start.year}",
            format="%d-%b-%Y"
        )
        end_dt = pd.to_datetime(
            f"{end_str}-{financial_year_start.year}",
            format="%d-%b-%Y"
        )

        return start_dt.date(), end_dt.date()

    # Year range: Apr-2017 to Mar-2018
    if re.match(r"^[A-Za-z]{3}-\d{4}\s+to\s+[A-Za-z]{3}-\d{4}$", period):
        start_str, end_str = period.split(" to ")

        start_dt = pd.to_datetime(start_str, format="%b-%Y")
        end_dt = pd.to_datetime(end_str, format="%b-%Y")

        start_date = start_dt.replace(day=1)
        end_date = end_dt.replace(
            day=calendar.monthrange(end_dt.year, end_dt.month)[1]
        )

        return start_date.date(), end_date.date()

    return None, None

def multi_transaction(report_name, from_date, to_date, period,file_name=None):

    xml_payload = f"""
    <ENVELOPE>
      <HEADER>
        <TALLYREQUEST>Export Data</TALLYREQUEST>
      </HEADER>
      <BODY>
        <EXPORTDATA>
          <REQUESTDESC>
            <REPORTNAME>{report_name}</REPORTNAME>
            <STATICVARIABLES>
              <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
              <SVFROMDATE>{from_date}</SVFROMDATE>
              <SVTODATE>{to_date}</SVTODATE>
              <SVPERIODICITY>{period}</SVPERIODICITY>
            </STATICVARIABLES>
          </REQUESTDESC>
        </EXPORTDATA>
      </BODY>
    </ENVELOPE>
    """

    response = requests.post(
        TALLY_URL, data=xml_payload, headers={"Content-Type": "application/xml"}
    )

    if response.status_code != 200:
        return []

    root = ET.fromstring(response.content)
    data = []

    periods = root.findall(".//DSPPERIOD")
    acc_infos = root.findall(".//DSPACCINFO")

    for period_tag, acc in zip(periods, acc_infos):
        period_value = period_tag.text.strip() if period_tag.text else ""
        debit = acc.findtext(".//DSPDRAMTA")
        credit = acc.findtext(".//DSPCRAMTA")
        closing = acc.findtext(".//DSPCLAMTA")

        data.append(
            {
                "Period": period_value,
                "Debit Amount": float(debit) if debit else 0.0,
                "Credit Amount": float(credit) if credit else 0.0,
                "Closing Amount": float(closing) if closing else 0.0,
            }
        )
    fy_start = pd.to_datetime(from_date, format="%Y%m%d")
    df = pd.DataFrame(data)

    df[["From Date", "To Date"]] = df["Period"].apply(lambda x: pd.Series(get_period_dates(x, fy_start)))

    

    return save_to_database(df, file_name) if file_name else df.to_dict(orient="records")





# ─────────────────────────────────────────
# PROFIT AND LOSS
# ─────────────────────────────────────────

def profit_and_loss_report(from_date, to_date,file_name=None):
    xml_request = f"""<ENVELOPE>
    <HEADER>
        <TALLYREQUEST>Export Data</TALLYREQUEST>
    </HEADER>
    <BODY>
        <EXPORTDATA>
            <REQUESTDESC>
                <REPORTNAME>Profit and Loss</REPORTNAME>
                <STATICVARIABLES>
                    <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
                    <SVFROMDATE>{from_date}</SVFROMDATE>
                    <SVTODATE>{to_date}</SVTODATE>
                    <EXPLODEFLAG>Yes</EXPLODEFLAG>
                </STATICVARIABLES>
            </REQUESTDESC>
        </EXPORTDATA>
    </BODY>
</ENVELOPE>"""

    response = requests.post(TALLY_URL, data=xml_request)

    if response.status_code != 200:
        raise Exception(f"Tally returned {response.status_code}")

    if "<html" in response.text.lower():
        raise Exception("Tally returned HTML instead of XML")

    root = ET.fromstring(response.text)
    rows = []
    current_name = None

    for elem in root.iter():
        if elem.tag == "BSNAME":
            name_elem = elem.find(".//DSPDISPNAME")
            if name_elem is not None and name_elem.text:
                current_name = name_elem.text.strip()

        elif elem.tag == "BSAMT" and current_name:
            sub_amt = elem.findtext("BSSUBAMT")
            main_amt = elem.findtext("BSMAINAMT")
            amount = sub_amt if sub_amt and sub_amt.strip() else main_amt
            rows.append({"Name": current_name, "Amount": amount if amount else "0"})
            current_name = None

    df = pd.DataFrame(rows)
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0.0)
    return save_to_database(df, file_name) if file_name else df.to_dict(orient="records")


# ─────────────────────────────────────────
# STOCK ANALYSER
# ─────────────────────────────────────────

def Stock_analzer(date_from, date_to, StockItemName,file_name=None):

    def clean_xml(xml_text):
        xml_text = re.sub(r"&#\d+;", "", xml_text)
        xml_text = re.sub(r"[^\x09\x0A\x0D\x20-\x7F]+", "", xml_text)
        return xml_text

    request_xml = f"""
    <ENVELOPE>
      <HEADER>
        <TALLYREQUEST>Export Data</TALLYREQUEST>
      </HEADER>
      <BODY>
        <EXPORTDATA>
          <REQUESTDESC>
            <REPORTNAME>STOCKVOUCHERS</REPORTNAME>
            <STATICVARIABLES>
              <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
              <SVFROMDATE>{date_from}</SVFROMDATE>
              <SVTODATE>{date_to}</SVTODATE>
              <STOCKITEMNAME>{StockItemName}</STOCKITEMNAME>
            
            </STATICVARIABLES>
          </REQUESTDESC>
        </EXPORTDATA>
      </BODY>
    </ENVELOPE>
    """

    response = requests.post(TALLY_URL, data=request_xml)

    if response.status_code != 200:
        return []

    try:
        root = ET.fromstring(clean_xml(response.text))
    except Exception as e:
        print("Stock XML Parse Error:", e)
        return []

    stock_rows = []
    current = {}

    for elem in root.iter():
        tag = elem.tag
        text = (elem.text or "").strip()

        if tag == "DSPVCHDATE":
            if current:
                stock_rows.append(current)
            current = {"Date": text}

        elif tag == "DSPVCHITEMACCOUNT":
            current["Party"] = text

        elif tag == "DSPVCHTYPE":
            current["Type"] = text

        elif tag == "DSPINBLOCK":
            current["InQty"] = elem.findtext("DSPVCHINQTY", default="")
            current["InAmt"] = elem.findtext("DSPVCHINAMT", default="")

        elif tag == "DSPOUTBLOCK":
            current["OutQty"] = elem.findtext("DSPVCHOUTQTY", default="")
            current["OutAmt"] = elem.findtext("DSPVCHNETTOUTAMT", default="")

        elif tag == "DSPCLBLOCK":
            current["ClosingQty"] = elem.findtext("DSPVCHCLQTY", default="")
            current["ClosingAmt"] = elem.findtext("DSPVCHCLAMT", default="")

        elif tag == "STKVCHTRACKQTY":
            current["TrackQty"] = text

    if current:
        stock_rows.append(current)

  
    df = pd.DataFrame(stock_rows)

    cols = [ "InAmt", "OutAmt", "ClosingAmt"]

    df[cols] = (
        df[cols]
        .apply(pd.to_numeric, errors="coerce")
        .fillna(0.0)
        .astype(float)
    )

    date_cols = ["Date"]
    df[date_cols] = df[date_cols].apply(pd.to_datetime, errors="coerce")
    return save_to_database(df, file_name) if file_name else df.to_dict(orient="records")


# ─────────────────────────────────────────
# STOCK GROUP SUMMARY
# ─────────────────────────────────────────

def _clean_qty(q):
    if not q:
        return ""
    return re.sub(r"[^\d.-]", "", q)


def _clean_float(val):
    if not val:
        return ""
    try:
        return float(val)
    except Exception:
        return ""

def Stock_Group_Summary(from_date, to_date, file_name=None):
    xml_request = f"""
    <ENVELOPE>
        <HEADER>
            <TALLYREQUEST>Export Data</TALLYREQUEST>
        </HEADER>
        <BODY>
            <EXPORTDATA>
                <REQUESTDESC>
                    <REPORTNAME>Stock Group Summary</REPORTNAME>
                    <STATICVARIABLES>
                        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
                        <SVFROMDATE>{from_date}</SVFROMDATE>
                        <SVTODATE>{to_date}</SVTODATE>
                        <EXPLODEFLAG>Yes</EXPLODEFLAG>
                    </STATICVARIABLES>
                </REQUESTDESC>
            </EXPORTDATA>
        </BODY>
    </ENVELOPE>
    """

    response = requests.post(
        TALLY_URL,
        data=xml_request,
        headers={"Content-Type": "application/xml"}
    )

    if response.status_code != 200:
        return []

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError:
        return []

    rows = []

    names = root.findall(".//DSPACCNAME")
    stocks = root.findall(".//DSPSTKINFO")

    for name_elem, stock_elem in zip(names, stocks):

        item_name = name_elem.findtext(
            "DSPDISPNAME",
            default=""
        ).strip()

        stk = stock_elem.find(".//DSPSTKCL")

        if stk is not None:
            qty = _clean_qty(
                stk.findtext("DSPCLQTY", "")
            )

            rate = _clean_float(
                stk.findtext("DSPCLRATE", "")
            )

            amount = _clean_float(
                stk.findtext("DSPCLAMTA", "")
            )

        else:
            qty = ""
            rate = ""
            amount = ""

        rows.append(
            {
                "Item Name": item_name,
                "Quantity": qty,
                "Rate": rate,
                "Amount": amount
            }
        )

    df = pd.DataFrame(rows)
    cols = ["Quantity", "Rate", "Amount"]
    df[cols] = df[cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)

    if file_name:
        return save_to_database(df, file_name)

    return rows

# ─────────────────────────────────────────
# MOVEMENT ANALYSIS
# ─────────────────────────────────────────

def _extract_number(text):
    if text and text.strip():
        match = re.findall(r"-?\d+\.?\d*", text)
        if match:
            return float(match[0])
    return 0.0

def Movenment_analaysis(
    from_date,
    to_date,
    file_name=None
):
    xml_request = f"""
    <ENVELOPE>
        <HEADER>
            <TALLYREQUEST>Export Data</TALLYREQUEST>
        </HEADER>
        <BODY>
            <EXPORTDATA>
                <REQUESTDESC>
                    <REPORTNAME>Movement Analysis</REPORTNAME>
                    <STATICVARIABLES>
                        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
                        <SVFROMDATE>{from_date}</SVFROMDATE>
                        <SVTODATE>{to_date}</SVTODATE>
                        <EXPLODEFLAG>Yes</EXPLODEFLAG>
                    </STATICVARIABLES>
                </REQUESTDESC>
            </EXPORTDATA>
        </BODY>
    </ENVELOPE>
    """

    response = requests.post(
        TALLY_URL,
        data=xml_request,
        headers={"Content-Type": "application/xml"}
    )

    if response.status_code != 200:
        return []

    if not response.text.strip():
        return []

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError:
        print("Invalid XML returned by Tally")
        print(response.text)
        return []

    rows = []
    current_item = None

    for elem in root.iter():

        if elem.tag == "DSPACCNAME":

            name_tag = elem.find("DSPDISPNAME")

            if (
                name_tag is not None
                and name_tag.text
            ):
                current_item = name_tag.text.strip()

        elif elem.tag == "STKANALINFO":

            stkmin = elem.find("STKMIN")
            stkout = elem.find("STKMOUT")

            rows.append(
                {
                    "Item": current_item,

                    "In Qty": _extract_number(
                        stkmin.findtext("STKINQTY")
                        if stkmin is not None
                        else None
                    ),

                    "In Value": _extract_number(
                        stkmin.findtext("STKINVALUE")
                        if stkmin is not None
                        else None
                    ),

                    "Out Qty": _extract_number(
                        stkout.findtext("STKOUTQTY")
                        if stkout is not None
                        else None
                    ),

                    "Out Value": _extract_number(
                        stkout.findtext("STKOUTVALUE")
                        if stkout is not None
                        else None
                    ),
                }
            )

    df = pd.DataFrame(rows)
    cols = [ "In Value", "Out Value"]

    df[cols] = df[cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)

    return (
        save_to_database(df, file_name)
        if file_name
        else rows
    )



def clean_qty(q):
    if not q:
        return 0.0

    match = re.search(r"[-+]?\d*\.?\d+", q)

    if match:
        return float(match.group())

    return 0.0


def clean_float(x):
    try:
        return float(x)
    except:
        return 0.0

def Stock_Category_Summary(from_date, to_date, file_name=None):

    xml_request = f"""
    <ENVELOPE>
        <HEADER>
            <TALLYREQUEST>Export Data</TALLYREQUEST>
        </HEADER>
        <BODY>
            <EXPORTDATA>
                <REQUESTDESC>
                    <REPORTNAME>Stock Category Summary</REPORTNAME>
                    <STATICVARIABLES>
                        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
                        <SVFROMDATE>{from_date}</SVFROMDATE>
                        <SVTODATE>{to_date}</SVTODATE>
                        
                    </STATICVARIABLES>
                </REQUESTDESC>
            </EXPORTDATA>
        </BODY>
    </ENVELOPE>
    """

    response = requests.post(
        TALLY_URL,
        data=xml_request,
        headers={"Content-Type": "application/xml"}
    )

    if response.status_code != 200:
        return []

    root = ET.fromstring(response.text)

    data_map = {}
    current_item = ""

    for elem in root.iter():

        if elem.tag == "DSPDISPNAME":
            current_item = elem.text.strip() if elem.text else ""

        elif elem.tag == "DSPSTKCL":

            qty = clean_qty(elem.findtext("DSPCLQTY", ""))
            rate = clean_float(elem.findtext("DSPCLRATE", ""))
            amount = clean_float(elem.findtext("DSPCLAMTA", ""))

            if qty == 0 and rate == 0 and amount == 0:
                continue

            if current_item not in data_map:
                data_map[current_item] = {
                    "Quantity": 0.0,
                    "Rate": rate,
                    "Amount": 0.0
                }

            data_map[current_item]["Quantity"] += qty
            data_map[current_item]["Amount"] += amount
            data_map[current_item]["Rate"] = rate

    rows = []

    for item, values in data_map.items():
        rows.append({
            "Item Name": item,
            "Quantity": float(values["Quantity"]),
            "Rate": float(values["Rate"]),
            "Amount": float(values["Amount"])
        })

    df = pd.DataFrame(rows)
    cols = ["Rate", "Amount"]
    df[cols] = df[cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)

    return save_to_database(df.head(100), file_name, len(df)) if file_name else df.to_dict(orient="records")




def Ratio_Analysis(from_date, to_date, file_name=None):

    xml_request = f"""
    <ENVELOPE>
        <HEADER>
            <TALLYREQUEST>Export Data</TALLYREQUEST>
        </HEADER>
        <BODY>
            <EXPORTDATA>
                <REQUESTDESC>
                    <REPORTNAME>Ratio Analysis</REPORTNAME>
                    <STATICVARIABLES>
                        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
                        <SVFROMDATE>{from_date}</SVFROMDATE>
                        <SVTODATE>{to_date}</SVTODATE>
                        <EXPLODEFLAG>Yes</EXPLODEFLAG>
                    </STATICVARIABLES>
                </REQUESTDESC>
            </EXPORTDATA>
        </BODY>
    </ENVELOPE>
    """

    response = requests.post(
        TALLY_URL,
        data=xml_request,
        headers={"Content-Type": "application/xml"}
    )

    if response.status_code != 200:
        return []

    root = ET.fromstring(response.text)

    def clean_value(value):
        if not value:
            return None, None, None

        value = value.strip()

        if "Dr" in value:
            nature = "Debit"
        elif "Cr" in value:
            nature = "Credit"
        else:
            nature = "Neutral"

        numeric = re.sub(r"[^\d.\-]", "", value.replace(",", ""))

        try:
            numeric = float(numeric)
        except:
            numeric = None

        return numeric, nature, value

    rows = []

    names = root.findall(".//RATIONAME")
    values = root.findall(".//RATIOVALUE")

    for name, value in zip(names, values):

        ratio_name = name.text.strip() if name.text else ""
        ratio_value = value.text.strip() if value.text else ""

        numeric, nature, original = clean_value(ratio_value)

        rows.append(
            {
                "Name": ratio_name,
                "Original Value": original,
                "Numeric Value": numeric,
                "Type": nature,
            }
        )

    df = pd.DataFrame(rows)
    cols = ["Numeric Value"]
    df[cols] = df[cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)   

    return save_to_database(df, file_name) if file_name else df.to_dict(orient="records")




def Negative_Ledgers_Report(from_date, to_date, file_name=None):

    xml_request = f"""
    <ENVELOPE>
        <HEADER>
            <TALLYREQUEST>Export Data</TALLYREQUEST>
        </HEADER>
        <BODY>
            <EXPORTDATA>
                <REQUESTDESC>
                    <REPORTNAME>Negative Ledgers</REPORTNAME>
                    <STATICVARIABLES>
                        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
                        <SVFROMDATE>{from_date}</SVFROMDATE>
                        <SVTODATE>{to_date}</SVTODATE>
                        <EXPLODEFLAG>Yes</EXPLODEFLAG>
                    </STATICVARIABLES>
                </REQUESTDESC>
            </EXPORTDATA>
        </BODY>
    </ENVELOPE>
    """

    response = requests.post(
        TALLY_URL,
        data=xml_request,
        headers={"Content-Type": "application/xml"}
    )

    if response.status_code != 200:
        return []

    root = ET.fromstring(response.text)

    rows = []
    ledger_name = None

    for elem in root:

        if elem.tag == "DSPACCNAME":
            ledger_name = elem.findtext("DSPDISPNAME", "").strip()

        elif elem.tag == "DSPACCINFO":

            debit = elem.findtext(
                "DSPCLDRAMT/DSPCLDRAMTA",
                default=""
            )

            credit = elem.findtext(
                "DSPCLCRAMT/DSPCLCRAMTA",
                default=""
            )

            rows.append(
                {
                    "Ledger Name": ledger_name,
                    "Debit": float(debit) if debit else 0.0,
                    "Credit": float(credit) if credit else 0.0,
                }
            )

    df = pd.DataFrame(rows)

    return save_to_database(df, file_name) if file_name else df.to_dict(orient="records")




def Order_Outstandings_Report(from_date, to_date, file_name=None):

    xml_request = f"""
    <ENVELOPE>
      <HEADER>
        <TALLYREQUEST>Export Data</TALLYREQUEST>
      </HEADER>

      <BODY>
        <EXPORTDATA>
          <REQUESTDESC>

            <REPORTNAME>Order Outstandings</REPORTNAME>

            <STATICVARIABLES>
              <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
              <SVFROMDATE>{from_date}</SVFROMDATE>
              <SVTODATE>{to_date}</SVTODATE>
            </STATICVARIABLES>

          </REQUESTDESC>
        </EXPORTDATA>
      </BODY>
    </ENVELOPE>
    """

    response = requests.post(
        TALLY_URL,
        data=xml_request,
        headers={"Content-Type": "application/xml"}
    )

    if response.status_code != 200:
        return []

    root = ET.fromstring(response.text)

    rows = []

    names = root.findall(".//DSPACCNAME")
    stocks = root.findall(".//ORDERSTKINFO")

    for name_tag, stock_tag in zip(names, stocks):

        item_name = name_tag.findtext(
            "DSPDISPNAME",
            default=""
        ).strip()

        qty = stock_tag.findtext(
            ".//ORDERCLQTY",
            default=""
        )

        rate = stock_tag.findtext(
            ".//ORDERCLRATE",
            default=""
        )

        amount = stock_tag.findtext(
            ".//ORDERCLAMTA",
            default=""
        )

        rows.append(
            {
                "Item Name": item_name,
                "Qty": qty,
                "Rate": rate,
                "Amount": amount,
            }
        )

    df = pd.DataFrame(rows)
    cols=['Rate','Amount']
    df[cols] = df[cols].apply(pd.to_numeric, errors="coerce").fillna(0.0) 


    return save_to_database(df, file_name) if file_name else df.to_dict(orient="records")

def Overdue_Payables_Report(
    from_date,
    to_date,
    file_name=None,
    ReportName=None
):

    xml_request = f"""
    <ENVELOPE>
        <HEADER>
            <TALLYREQUEST>Export Data</TALLYREQUEST>
        </HEADER>
        <BODY>
            <EXPORTDATA>
                <REQUESTDESC>
                    <REPORTNAME>{ReportName}</REPORTNAME>
                    <STATICVARIABLES>
                        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
                        <SVFROMDATE>{from_date}</SVFROMDATE>
                        <SVTODATE>{to_date}</SVTODATE>
                        <EXPLODEFLAG>Yes</EXPLODEFLAG>
                    </STATICVARIABLES>
                </REQUESTDESC>
            </EXPORTDATA>
        </BODY>
    </ENVELOPE>
    """

    response = requests.post(
        TALLY_URL,
        data=xml_request,
        headers={"Content-Type": "application/xml"}
    )

    if response.status_code != 200:
        return []

    root = ET.fromstring(response.text)

    rows = []
    current_invoice = {}
    items = []

    for elem in root.iter():

        tag = elem.tag.upper()
        value = elem.text.strip() if elem.text else ""

        if tag == "BILLDATE":
            current_invoice["Date"] = value

        elif tag == "BILLREF":
            current_invoice["Reference"] = value

        elif tag == "BILLPARTY":
            current_invoice["Party"] = value

        elif tag == "BILLVCHNUMBER":
            current_invoice["Voucher No"] = value

        elif tag == "BILLVCHTYPE":
            current_invoice["Voucher Type"] = value

        elif tag == "BILLVCHAMOUNT":
            current_invoice["Amount"] = value

        elif tag == "BILLDUE":
            current_invoice["Due Date"] = value

        elif tag == "BILLOVERDUE":
            current_invoice["Overdue Days"] = value

        elif tag == "BILLCL":
            current_invoice["Closing Balance"] = value

        elif tag == "BILLINVITEM":
            items.append({
                "Item": value
            })

        elif tag == "BILLINVRATE":
            if items:
                items[-1]["Rate"] = value

        elif tag == "BILLINVQTY":
            if items:
                items[-1]["Qty"] = value

        elif tag == "BILLFIXED":

            if current_invoice and items:

                for item in items:
                    rows.append({
                        **current_invoice,
                        **item
                    })

            elif current_invoice:
                rows.append(current_invoice)

            current_invoice = {}
            items = []

    # Final Flush
    if current_invoice:

        if items:

            for item in items:
                rows.append({
                    **current_invoice,
                    **item
                })

        else:
            rows.append(current_invoice)

    if not rows:
        return []

    df = pd.DataFrame(rows)

    # -----------------------------
    # DATE FILTERING
    # -----------------------------
    if "Date" in df.columns:

        # Example: 8-Dec-10
        df["Date"] = pd.to_datetime(
            df["Date"],
            format="%d-%b-%y",
            errors="coerce"
        )

        from_dt = pd.to_datetime(
            from_date,
            format="%Y%m%d",
            errors="coerce"
        )

        to_dt = pd.to_datetime(
            to_date,
            format="%Y%m%d",
            errors="coerce"
        )

        df = df[
            (df["Date"] >= from_dt)
            & (df["Date"] <= to_dt)
        ]

        # Convert back for API output
        if not df.empty:
            df["Date"] = df["Date"].dt.strftime("%d-%b-%y")

    # -----------------------------
    # CLEAN NUMERIC COLUMNS
    # -----------------------------
    col=['Overdue Days','Closing Balance']
    df[col]=df[col].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    col=['Date','Due Date"']
    df=df['']
  
    
    

    # Replace NaN with None for FastAPI JSON
    df = df.astype(object)
    df = df.where(pd.notnull(df), None)

   

    if file_name:
        return save_to_database(df, file_name)

    return df.to_dict(orient="records")




def Trial_Balance_Report(
    from_date,
    to_date,
    is_ledgerwise="NO",
    file_name=None
):

    xml_request = f"""
    <ENVELOPE>
        <HEADER>
            <TALLYREQUEST>Export Data</TALLYREQUEST>
        </HEADER>
        <BODY>
            <EXPORTDATA>
                <REQUESTDESC>
                    <REPORTNAME>Trial Balance</REPORTNAME>
                    <STATICVARIABLES>
                        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
                        <SVFROMDATE>{from_date}</SVFROMDATE>
                        <SVTODATE>{to_date}</SVTODATE>
                        <ISLEDGERWISE>{is_ledgerwise}</ISLEDGERWISE>
                        
                    </STATICVARIABLES>
                </REQUESTDESC>
            </EXPORTDATA>
        </BODY>
    </ENVELOPE>
    """

    response = requests.post(
        TALLY_URL,
        data=xml_request,
        headers={"Content-Type": "application/xml"}
    )

    if response.status_code != 200:
        return []

    root = ET.fromstring(response.text)

    rows = []
    current_name = None

    for elem in root.iter():

        if elem.tag == "DSPDISPNAME":
            current_name = (
                elem.text.strip()
                if elem.text else ""
            )

        elif elem.tag == "DSPACCINFO":

            dr_elem = elem.find(".//DSPCLDRAMTA")
            cr_elem = elem.find(".//DSPCLCRAMTA")

            debit = (
                dr_elem.text.strip()
                if dr_elem is not None and dr_elem.text
                else "0"
            )

            credit = (
                cr_elem.text.strip()
                if cr_elem is not None and cr_elem.text
                else "0"
            )

            rows.append(
                {
                    "Account Name": current_name,
                    "Debit": debit,
                    "Credit": credit,
                }
            )

    df = pd.DataFrame(rows)
    

    if "Debit" in df.columns:
        df["Debit"] = pd.to_numeric(
            df["Debit"],
            errors="coerce"
        ).fillna(0)

    if "Credit" in df.columns:
        df["Credit"] = pd.to_numeric(
            df["Credit"],
            errors="coerce"
        ).fillna(0)

    return (
        save_to_database(df, file_name)
        if file_name
        else df.to_dict(orient="records")
    )



def Balance_Sheet_Report(
    from_date,
    to_date,
    file_name=None
):

    xml_request = f"""
    <ENVELOPE>
        <HEADER>
            <TALLYREQUEST>Export Data</TALLYREQUEST>
        </HEADER>
        <BODY>
            <EXPORTDATA>
                <REQUESTDESC>
                    <REPORTNAME>Balance Sheet</REPORTNAME>
                    <STATICVARIABLES>
                        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
                        <SVFROMDATE>{from_date}</SVFROMDATE>
                        <SVTODATE>{to_date}</SVTODATE>
                     
                        <EXPLODEFLAG>Yes</EXPLODEFLAG>
                    </STATICVARIABLES>
                </REQUESTDESC>
            </EXPORTDATA>
        </BODY>
    </ENVELOPE>
    """

    response = requests.post(
        TALLY_URL,
        data=xml_request,
        headers={"Content-Type": "application/xml"}
    )

    if response.status_code != 200:
        return []

    root = ET.fromstring(response.text)

    rows = []

    bsnames = root.findall(".//BSNAME")
    bsamts = root.findall(".//BSAMT")

    for name_tag, amt_tag in zip(bsnames, bsamts):

        name_tag_val = name_tag.find(".//DSPDISPNAME")

        ledger_name = (
            name_tag_val.text.strip()
            if name_tag_val is not None and name_tag_val.text
            else ""
        )

        main_amt = amt_tag.find("BSMAINAMT")
        sub_amt = amt_tag.find("BSSUBAMT")

        amount = ""

        if (
            main_amt is not None
            and main_amt.text
            and main_amt.text.strip()
        ):
            amount = main_amt.text.strip()

        elif (
            sub_amt is not None
            and sub_amt.text
            and sub_amt.text.strip()
        ):
            amount = sub_amt.text.strip()

        if ledger_name or amount:

            rows.append(
                {
                    "Ledger Name": ledger_name,
                    "Amount": amount
                }
            )

    df = pd.DataFrame(rows)

    if "Amount" in df.columns:
        df["Amount"] = pd.to_numeric(
            df["Amount"],
            errors="coerce"
        ).fillna(0)

    return (
        save_to_database(df, file_name)
        if file_name
        else df.to_dict(orient="records")
    )



def Cost_Center_Summary_Report(
    from_date,
    to_date,
    file_name=None
):

    xml_request = f"""
    <ENVELOPE>
        <HEADER>
            <TALLYREQUEST>Export Data</TALLYREQUEST>
        </HEADER>
        <BODY>
            <EXPORTDATA>
                <REQUESTDESC>
                    <REPORTNAME>Cost Centre Summary</REPORTNAME>
                    <STATICVARIABLES>
                        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
                        <SVFROMDATE>{from_date}</SVFROMDATE>
                        <SVTODATE>{to_date}</SVTODATE>
                        <EXPLODEFLAG>Yes</EXPLODEFLAG>
                    </STATICVARIABLES>
                </REQUESTDESC>
            </EXPORTDATA>
        </BODY>
    </ENVELOPE>
    """

    response = requests.post(
        TALLY_URL,
        data=xml_request,
        headers={"Content-Type": "application/xml"}
    )

    if response.status_code != 200:
        return []

    root = ET.fromstring(response.text)

    rows = []

    names = root.findall(".//DSPACCNAME")
    infos = root.findall(".//DSPACCINFO")

    for name_node, info_node in zip(names, infos):

        name = name_node.findtext(
            "DSPDISPNAME",
            default=""
        ).strip()

        dr = info_node.findtext(
            "./DSPDRAMT/DSPDRAMTA",
            default="0"
        )

        cr = info_node.findtext(
            "./DSPCRAMT/DSPCRAMTA",
            default="0"
        )

        cl = info_node.findtext(
            "./DSPCLAMT/DSPCLAMTA",
            default="0"
        )

        rows.append(
            {
                "Cost Center": name,
                "Debit": float(dr) if dr else 0,
                "Credit": float(cr) if cr else 0,
                "Closing": float(cl) if cl else 0
            }
        )

    df = pd.DataFrame(rows)

    return (
        save_to_database(df, file_name)
        if file_name
        else df.to_dict(orient="records")
    )


def Godown_Summary_Report(
    from_date,
    to_date,
    file_name=None
):

    xml_request = f"""
    <ENVELOPE>
        <HEADER>
            <TALLYREQUEST>Export Data</TALLYREQUEST>
        </HEADER>
        <BODY>
            <EXPORTDATA>
                <REQUESTDESC>
                    <REPORTNAME>Godown Summary</REPORTNAME>
                    <STATICVARIABLES>
                        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
                        <SVFROMDATE>{from_date}</SVFROMDATE>
                        <SVTODATE>{to_date}</SVTODATE>
                        <EXPLODEFLAG>Yes</EXPLODEFLAG>
                    </STATICVARIABLES>
                </REQUESTDESC>
            </EXPORTDATA>
        </BODY>
    </ENVELOPE>
    """

    response = requests.post(
        TALLY_URL,
        data=xml_request,
        headers={"Content-Type": "application/xml"}
    )

    if response.status_code != 200:
        return []

    root = ET.fromstring(response.text)

    rows = []
    current_name = None

    for elem in root.iter():

        if elem.tag == "DSPDISPNAME":
            current_name = (
                elem.text.strip()
                if elem.text else ""
            )

        elif elem.tag == "DSPSTKCL":

            qty = elem.findtext(
                "DSPCLQTY",
                default=""
            )

            rate = elem.findtext(
                "DSPCLRATE",
                default=""
            )

            amount = elem.findtext(
                "DSPCLAMTA",
                default=""
            )

            rows.append(
                {
                    "Name": current_name,
                    "Quantity": qty,
                    "Rate": rate,
                    "Amount": amount
                }
            )

    df = pd.DataFrame(rows)
    col=['Rate','Amount']
    df[col]=df[col].apply(pd.to_numeric, errors="coerce").fillna(0.0)

    return (
        save_to_database(df, file_name)
        if file_name
        else df.to_dict(orient="records")
    )
def Statistics_Report(
    from_date,
    to_date,
    file_name=None
):

    xml_request = f"""
    <ENVELOPE>
        <HEADER>
            <TALLYREQUEST>Export Data</TALLYREQUEST>
        </HEADER>
        <BODY>
            <EXPORTDATA>
                <REQUESTDESC>
                    <REPORTNAME>Statistics</REPORTNAME>
                    <STATICVARIABLES>
                        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
                        <SVFROMDATE>{from_date}</SVFROMDATE>
                        <SVTODATE>{to_date}</SVTODATE>
                        <EXPLODEFLAG>Yes</EXPLODEFLAG>
                    </STATICVARIABLES>
                </REQUESTDESC>
            </EXPORTDATA>
        </BODY>
    </ENVELOPE>
    """

    response = requests.post(
        TALLY_URL,
        data=xml_request,
        headers={"Content-Type": "application/xml"}
    )

    if response.status_code != 200:
        return []

    root = ET.fromstring(response.text)

    rows = []

    stat_names = root.findall(".//STATNAME")
    stat_values = root.findall(".//STATVALUE")

    for name_tag, value_tag in zip(stat_names, stat_values):

        name = (
            name_tag.text.strip()
            if name_tag is not None and name_tag.text
            else ""
        )

        direct = value_tag.findtext(
            "STATDIRECT",
            default="0"
        )

        cancelled = value_tag.findtext(
            "STATCANCELLED",
            default=""
        )

        rows.append(
            {
                "Name": name,
                "Count": direct,
                "Cancelled": cancelled
            }
        )

    df = pd.DataFrame(rows)

    if "Count" in df.columns:
        df["Count"] = pd.to_numeric(
            df["Count"],
            errors="coerce"
        ).fillna(0)

    return (
        save_to_database(df, file_name)
        if file_name
        else df.to_dict(orient="records")
    )


def Stock_Purchase_Report(
    stock_item,
    from_date,
    to_date,
    file_name=None
):
    xml_request = f"""
    <ENVELOPE>
        <HEADER>
            <TALLYREQUEST>Export Data</TALLYREQUEST>
        </HEADER>
        <BODY>
            <EXPORTDATA>
                <REQUESTDESC>
                    <REPORTNAME>Stock Query</REPORTNAME>
                    <STATICVARIABLES>
                        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
                        <SVFROMDATE>{from_date}</SVFROMDATE>
                        <SVTODATE>{to_date}</SVTODATE>
                        <StockItemName>{stock_item}</StockItemName>
                    </STATICVARIABLES>
                </REQUESTDESC>
            </EXPORTDATA>
        </BODY>
    </ENVELOPE>
    """

    try:
        response = requests.post(
            TALLY_URL,
            data=xml_request,
            headers={"Content-Type": "application/xml"}
        )

        response.raise_for_status()

       

        root = ET.fromstring(response.text)

        dates = [e.text or "" for e in root.findall(".//STQSALESDATE")]
        Party_name = [e.text or "" for e in root.findall(".//STQSALESVCHNO")]
        qtys = [e.text or "" for e in root.findall(".//STQSALESVCHQTY")]
        rates = [e.text or "" for e in root.findall(".//STQSALESVCHRATE")]
        discounts = [e.text or "" for e in root.findall(".//STQSALESVCHDISC")]
        amounts = [e.text or "" for e in root.findall(".//STQSALESVCHAMOUNT")]
        godowns = [e.text or "" for e in root.findall(".//STQGODOWNNAME")]
        batches = [e.text or "" for e in root.findall(".//STQBATCHNAME")]
        stock_qtys = [e.text or "" for e in root.findall(".//STQGODOWNQTY")]



        max_rows = max(
            [
                len(dates),
                len(Party_name),
                len(qtys),
                len(rates),
                len(discounts),
                len(amounts),
                len(godowns),
                len(batches),
                len(stock_qtys)
            ],
            default=0
        )

        rows = []

        for i in range(max_rows):
            rows.append({
                "Date": dates[i] if i < len(dates) else "",
                "Party_name": Party_name[i] if i < len(Party_name) else "",
                "Qty": qtys[i] if i < len(qtys) else "",
                "Rate": rates[i] if i < len(rates) else "",
                "Discount": discounts[i] if i < len(discounts) else "",
                "Amount": amounts[i] if i < len(amounts) else "",
                "Godown": godowns[i] if i < len(godowns) else "",
                "Batch": batches[i] if i < len(batches) else "",
                "StockQty": stock_qtys[i] if i < len(stock_qtys) else ""
            })

        df = pd.DataFrame(rows)
        col=['Amount','Discount','Rate']
        date_col=['Date']
        df[date_col] = df[date_col].apply(pd.to_datetime, errors="coerce")
        df[col] = (
    df[col]
    .apply(pd.to_numeric, errors="coerce")
    .fillna(0.0)
    .astype(float))


        return (
            save_to_database(df, file_name)
            if file_name
            else df.to_dict(orient="records")
        )

    except requests.exceptions.RequestException as e:
        return [{"error": f"Connection Error: {str(e)}"}]

    except ET.ParseError as e:
        return [{"error": f"XML Parse Error: {str(e)}"}]