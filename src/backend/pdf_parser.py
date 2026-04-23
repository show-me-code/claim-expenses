"""
PDF Parser Module - Extract information from train tickets and hotel invoices.
"""
import os
import json
import pdfplumber
import re
from datetime import datetime
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass


@dataclass
class TrainTicket:
    """Train ticket data structure."""
    file_path: str
    invoice_number: str
    departure_station: str
    arrival_station: str
    train_number: str
    date: datetime
    time: str
    seat: str
    price: float
    passenger_name: str
    ticket_type: str  # 'outbound', 'return', 'refund'


@dataclass
class HotelInvoice:
    """Hotel invoice data structure."""
    file_path: str
    invoice_number: str
    issue_date: datetime
    hotel_name: str
    days: int
    amount: float
    tax: float
    total: float


def parse_train_ticket_pdf(file_path: str) -> Optional[TrainTicket]:
    """Parse a train ticket PDF and extract ticket information."""
    try:
        with pdfplumber.open(file_path) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() or ""

        # Extract invoice number - handle Chinese/English colon
        invoice_match = re.search(r'发票号码[：:\s]*(\d+)', text)
        invoice_number = invoice_match.group(1) if invoice_match else ""

        # Extract stations - use more general patterns
        # Pattern for Chinese station names: 城市名 + 南站/北站/东站/西站/站
        station_pattern = r'([一-龥]{2,4}[南站北站东站西站站]|[一-龥]{2,4}站)'
        stations = re.findall(station_pattern, text)

        # Filter out duplicates and sort by appearance
        stations = list(dict.fromkeys(stations))  # Remove duplicates, preserve order

        # Determine departure and arrival stations based on English station order
        # English stations appear in order: departure -> arrival
        departure_station = ""
        arrival_station = ""

        # Extract English station names for ordering (more reliable)
        english_pattern = r'([A-Z][a-z]+nan|[A-Z][a-z]+)'
        english_stations = re.findall(english_pattern, text)

        if len(english_stations) >= 2:
            # Use English order to determine departure/arrival
            first_english = english_stations[0].lower()

            # Find matching Chinese station
            # Map: beijingnan -> 北京南站, nanjingnan -> 南京南站, etc.
            english_to_chinese = {
                'beijingnan': '北京南站', 'beijing': '北京站',
                'nanjingnan': '南京南站', 'nanjing': '南京站',
                'shanghai': '上海站', 'shanghainan': '上海南站',
                'guangzhounan': '广州南站', 'guangzhou': '广州站',
                'shenzhen': '深圳站', 'shenzhenbei': '深圳北站',
            }

            # Get Chinese stations in order
            chinese_from_english = []
            for eng in english_stations[:2]:
                eng_lower = eng.lower()
                if eng_lower in english_to_chinese:
                    chinese_from_english.append(english_to_chinese[eng_lower])

            if len(chinese_from_english) >= 2:
                departure_station = chinese_from_english[0]
                arrival_station = chinese_from_english[1]
            elif len(stations) >= 2:
                # Fallback: match English order with Chinese stations found
                # First English corresponds to departure
                for s in stations:
                    if any(city in s for city in ['北京', '南京', '上海', '广州', '深圳', '成都', '杭州', '武汉', '西安']):
                        if not departure_station:
                            departure_station = s
                        elif not arrival_station and s != departure_station:
                            arrival_station = s

        elif len(stations) >= 2:
            # Fallback: use order of appearance
            departure_station = stations[0]
            arrival_station = stations[1]
        elif len(stations) == 1:
            # Only one station found, can't determine direction
            departure_station = stations[0]
            arrival_station = ""

        # Extract train number (G/D/C followed by numbers)
        train_match = re.search(r'(G\d+|D\d+|C\d+|K\d+|T\d+)', text)
        train_number = train_match.group(1) if train_match else ""

        # Extract date - prioritize travel date over invoice issue date
        # Travel date appears right before "开" (time), e.g., "2026年01月25日 12:00开"
        # Invoice issue date appears as "开票日期:2026年03月25日"
        date_pattern = r'(\d{4})[年\-](\d{1,2})[月\-](\d{1,2})日?'

        # Find date that appears right before time (travel date)
        travel_date_pattern = r'(\d{4})[年\-](\d{1,2})[月\-](\d{1,2})日?\s*\d{1,2}:\d{2}开'
        travel_date_match = re.search(travel_date_pattern, text)

        if travel_date_match:
            year, month, day = travel_date_match.groups()
            date = datetime(int(year), int(month), int(day))
        else:
            # Fallback: find date after English station names
            english_pattern = r'(Beijingnan|Nanjingnan).*?(\d{4})[年\-](\d{1,2})[月\-](\d{1,2})日?'
            english_match = re.search(english_pattern, text, re.IGNORECASE)
            if english_match:
                year, month, day = english_match.groups()[1:4]
                date = datetime(int(year), int(month), int(day))
            else:
                # Last fallback: first date in document (may be wrong)
                date_match = re.search(date_pattern, text)
                if date_match:
                    year, month, day = date_match.groups()
                    date = datetime(int(year), int(month), int(day))
                else:
                    date = datetime.now()

        # Extract time (format: 12:00开)
        time_match = re.search(r'(\d{1,2}:\d{2})开', text)
        time = time_match.group(1) if time_match else ""

        # Extract seat number (format: 14车13A号)
        seat_match = re.search(r'(\d+车\d+[A-Z]号)', text)
        seat = seat_match.group(1) if seat_match else ""

        # Extract price (format: ￥533.00 or Y533.00)
        price_pattern = r'[￥¥Y]?\s*(\d+\.\d{2})'
        price_match = re.search(price_pattern, text)
        # For train tickets, look for "票价" label
        price_label_match = re.search(r'票价[:\s]*[￥¥Y]?\s*(\d+\.\d{2})', text)
        if price_label_match:
            price = float(price_label_match.group(1))
        elif price_match:
            price = float(price_match.group(1))
        else:
            price = 0.0

        # Check if this is a refund ticket
        is_refund = '退票费' in text or '退票' in text

        # Extract passenger name
        name_match = re.search(r'(\d{18}\*{4}\d{4})\s*([一-龥]+)', text)
        passenger_name = name_match.group(2) if name_match else ""

        # Determine ticket type based on departure station
        if is_refund:
            ticket_type = 'refund'
        elif '北京' in departure_station:
            ticket_type = 'outbound'
        else:
            ticket_type = 'return'

        return TrainTicket(
            file_path=file_path,
            invoice_number=invoice_number,
            departure_station=departure_station,
            arrival_station=arrival_station,
            train_number=train_number,
            date=date,
            time=time,
            seat=seat,
            price=price,
            passenger_name=passenger_name,
            ticket_type=ticket_type
        )
    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
        return None


def parse_hotel_invoice_pdf(file_path: str) -> Optional[HotelInvoice]:
    """Parse a hotel invoice PDF and extract invoice information."""
    try:
        with pdfplumber.open(file_path) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() or ""

        # Extract invoice number - handle Chinese/English colon
        # Format: "发票号码：26322000000821253661" (Chinese colon) or "发票号码:xxx"
        invoice_match = re.search(r'发票号码[：:\s]*(\d{20})', text)
        if not invoice_match:
            # Try without fixed length
            invoice_match = re.search(r'发票号码[：:\s]*(\d+)', text)
        invoice_number = invoice_match.group(1) if invoice_match else ""

        # Extract issue date (开票日期)
        date_pattern = r'(\d{4})[年\-](\d{1,2})[月\-](\d{1,2})日?'
        date_match = re.search(date_pattern, text)
        if date_match:
            year, month, day = date_match.groups()
            issue_date = datetime(int(year), int(month), int(day))
        else:
            issue_date = datetime.now()

        # Extract hotel name - look for company name pattern
        # Format: "南京黄埔大酒店有限公司" etc.
        hotel_pattern = r'([一-龥]+酒店[一-龥]*有限公司|[一-龥]+酒店)'
        hotel_match = re.search(hotel_pattern, text)
        hotel_name = hotel_match.group(1) if hotel_match else ""

        # ========== 先提取金额信息 ==========
        # Extract total amount (价税合计)
        # Format: "壹仟玖佰圆整 ¥1900.00" or "¥1900.00"
        total_pattern = r'[￥¥]?\s*(\d+\.\d{2})'
        # Look for "价税合计" or "合计"
        total_match = re.search(r'(价税合计|合计).*?[￥¥]?\s*(\d+\.\d{2})', text)
        if total_match:
            total = float(total_match.group(2))
        else:
            # Fallback: find the last price in the document
            all_prices = re.findall(total_pattern, text)
            total = float(all_prices[-1]) if all_prices else 0.0

        # Extract unit price (单价) - 住宿每晚单价
        unit_price = 0.0
        # 表格格式：住宿服务 数量 单价 金额
        # 例如：住宿服务 5 ¥380.00 ¥1900.00
        # 单价是第二个金额数字
        unit_price_match = re.search(r'住宿服务[^\d]*(\d+)[^\d]*(\d+\.\d{2})[^\d]*(\d+\.\d{2})', text)
        if unit_price_match:
            unit_price = float(unit_price_match.group(2))  # 第二个数字是单价

        # ========== 再提取住宿天数 ==========
        days = 1  # 默认1天

        # 方法1：表格数量列格式（最精确）
        # 格式：住宿服务 数量 单价 金额
        if unit_price_match:
            days = int(unit_price_match.group(1))  # 第一个数字是数量（天数）

        # 方法2：查找"住宿"相关的天数，如 "住宿5天" "住宿服务*5天"
        if days == 1:
            stay_days_match = re.search(r'住宿[^0-9]*(\d+)\s*天', text)
            if stay_days_match:
                days = int(stay_days_match.group(1))

        # 方法3：查找"天"后面或前面的数字
        if days == 1:
            # "天" 后面有数字：天5
            days_match = re.search(r'天\s*(\d+)', text)
            if days_match:
                days = int(days_match.group(1))

        # 方法4：数字后面有"天"：5天
        if days == 1:
            days_match2 = re.search(r'(\d+)\s*天', text)
            if days_match2:
                days = int(days_match2.group(1))

        # 方法5：通过单价反推天数（单价已提取）
        if days == 1 and unit_price > 0 and total > 0:
            calculated_days = round(total / unit_price)
            if calculated_days >= 1 and calculated_days <= 30:
                days = calculated_days

        # Extract amount without tax (金额)
        amount_match = re.search(r'金额\s*[￥¥]?\s*(\d+\.\d{2})', text)
        if amount_match:
            amount = float(amount_match.group(1))
        else:
            # Try to find amount row
            amount_pattern = r'(\d+\.\d{2})\s*\d+%\s*\d+\.\d{2}'
            amount_match2 = re.search(amount_pattern, text)
            if amount_match2:
                amount = float(amount_match2.group(1))
            else:
                amount = total / 1.06  # Assume 6% tax rate

        # Extract tax amount
        tax_match = re.search(r'税额\s*[￥¥]?\s*(\d+\.\d{2})', text)
        if tax_match:
            tax = float(tax_match.group(1))
        else:
            tax = total - amount

        return HotelInvoice(
            file_path=file_path,
            invoice_number=invoice_number,
            issue_date=issue_date,
            hotel_name=hotel_name,
            days=days,
            amount=amount,
            tax=tax,
            total=total
        )
    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
        return None


def is_train_ticket_pdf(text: str) -> bool:
    """Check if PDF is a train ticket based on content."""
    # More specific keywords for train tickets
    primary_keywords = ['电子发票（铁路电子客票）', '铁路电子客票', '12306', '中国铁路']
    secondary_keywords = ['票价', 'G11', 'G744', '车']  # Train-specific keywords

    # Must have primary keyword OR both secondary conditions
    has_primary = any(kw in text for kw in primary_keywords)
    has_secondary = any(kw in text for kw in secondary_keywords) and '开票日期' in text

    return has_primary or has_secondary


def is_hotel_invoice_pdf(text: str) -> bool:
    """Check if PDF is a hotel invoice based on content."""
    # More specific keywords for hotel invoices
    keywords = ['住宿服务', '住宿费', '电子发票（普通发票）', '酒店有限公司']
    return any(kw in text for kw in keywords)


# 已处理发票记录文件路径
PROCESSED_RECORD_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'processed_invoices.json')


def load_processed_records() -> dict:
    """加载已处理的发票记录"""
    if os.path.exists(PROCESSED_RECORD_FILE):
        try:
            with open(PROCESSED_RECORD_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {'tickets': [], 'invoices': []}
    return {'tickets': [], 'invoices': []}


def save_processed_records(records: dict):
    """保存已处理的发票记录"""
    with open(PROCESSED_RECORD_FILE, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def clear_processed_records():
    """清除已处理的发票记录"""
    if os.path.exists(PROCESSED_RECORD_FILE):
        os.remove(PROCESSED_RECORD_FILE)


def parse_all_pdfs(root_folder: str, skip_processed: bool = True) -> Tuple[List[TrainTicket], List[HotelInvoice]]:
    """
    Parse all PDFs in a folder and categorize them.

    Args:
        root_folder: 根文件夹路径
        skip_processed: 是否跳过已处理的发票（防止重复计算）

    Returns:
        (tickets, invoices) 解析出的票据和发票列表
    """
    import json

    tickets = []
    invoices = []

    # 加载已处理记录
    processed = load_processed_records() if skip_processed else {'tickets': [], 'invoices': []}
    processed_tickets = set(processed.get('tickets', []))
    processed_invoices = set(processed.get('invoices', []))

    # 新处理的发票号码（用于更新记录）
    new_ticket_numbers = []
    new_invoice_numbers = []

    for root, dirs, files in os.walk(root_folder):
        for file in files:
            if file.lower().endswith('.pdf'):
                file_path = os.path.join(root, file)

                # First check file type by reading content
                try:
                    with pdfplumber.open(file_path) as pdf:
                        text = ""
                        for page in pdf.pages:
                            text += page.extract_text() or ""

                    if is_train_ticket_pdf(text):
                        ticket = parse_train_ticket_pdf(file_path)
                        if ticket:
                            # 检查是否已处理过
                            if ticket.invoice_number and ticket.invoice_number in processed_tickets:
                                print(f"[跳过] 已处理的车票: {ticket.invoice_number}")
                                continue
                            tickets.append(ticket)
                            if ticket.invoice_number:
                                new_ticket_numbers.append(ticket.invoice_number)

                    elif is_hotel_invoice_pdf(text):
                        invoice = parse_hotel_invoice_pdf(file_path)
                        if invoice:
                            # 检查是否已处理过
                            if invoice.invoice_number and invoice.invoice_number in processed_invoices:
                                print(f"[跳过] 已处理的发票: {invoice.invoice_number}")
                                continue
                            invoices.append(invoice)
                            if invoice.invoice_number:
                                new_invoice_numbers.append(invoice.invoice_number)

                except Exception as e:
                    print(f"Error reading {file_path}: {e}")
                    continue

    # 更新已处理记录
    if skip_processed and (new_ticket_numbers or new_invoice_numbers):
        processed['tickets'] = list(processed_tickets | set(new_ticket_numbers))
        processed['invoices'] = list(processed_invoices | set(new_invoice_numbers))
        save_processed_records(processed)
        print(f"[记录] 新增 {len(new_ticket_numbers)} 张车票, {len(new_invoice_numbers)} 张发票到已处理列表")

    return tickets, invoices