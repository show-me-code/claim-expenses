"""
Expense Calculator Module - Calculate total expenses for trips.
"""
from datetime import datetime, timedelta
from typing import List, Dict, Set, Tuple, Optional
from dataclasses import dataclass, field

from .trip_matcher import Trip, get_city_base
from .pdf_parser import HotelInvoice


@dataclass
class TripExpense:
    """Expense summary for a single trip."""
    trip_id: int
    trip: Trip
    hotel_invoices: List[HotelInvoice] = field(default_factory=list)
    hotel_total: float = 0.0
    meal_allowance: float = 0.0
    daily_meal_rate: float = 100.0
    grand_total: float = 0.0

    def calculate(self):
        """Calculate all expense totals."""
        self.hotel_total = sum(inv.total for inv in self.hotel_invoices)
        self.meal_allowance = self.trip.days * self.daily_meal_rate
        self.grand_total = self.trip.ticket_total + self.trip.refund_total + self.hotel_total + self.meal_allowance


@dataclass
class ExpenseSummary:
    """Complete expense summary for all trips."""
    trip_expenses: List[TripExpense] = field(default_factory=list)
    total_tickets: float = 0.0
    total_refunds: float = 0.0
    total_hotels: float = 0.0
    total_meals: float = 0.0
    grand_total: float = 0.0
    hotel_match_results: List[Dict] = field(default_factory=list)  # 酒店匹配结果详情

    def calculate(self):
        """Calculate grand totals."""
        self.total_tickets = sum(te.trip.ticket_total for te in self.trip_expenses)
        self.total_refunds = sum(te.trip.refund_total for te in self.trip_expenses)
        self.total_hotels = sum(te.hotel_total for te in self.trip_expenses)
        self.total_meals = sum(te.meal_allowance for te in self.trip_expenses)
        self.grand_total = sum(te.grand_total for te in self.trip_expenses)


def match_hotel_to_trip(trip: Trip, invoice: HotelInvoice) -> Tuple[float, str]:
    """
    计算酒店发票与行程的匹置信度

    Args:
        trip: 行程对象
        invoice: 酒店发票对象

    Returns:
        (匹置信度, 匹配原因说明)
    """
    confidence = 0.0
    reasons = []

    # 1. 城市匹配（最重要的因素）
    dest_city = get_city_base(trip.destination_city or trip.arrival_city)
    hotel_city = get_city_base(invoice.hotel_name) if invoice.hotel_name else ''

    if dest_city and hotel_city:
        if dest_city == hotel_city:
            confidence += 0.5
            reasons.append(f"城市精确匹配: {dest_city}")
        elif dest_city in invoice.hotel_name:
            confidence += 0.4
            reasons.append(f"城市名称匹配: {dest_city} in {invoice.hotel_name}")

    # 2. 日期匹配
    if trip.start_date and trip.end_date and invoice.issue_date:
        # 发票日期应在行程范围内或行程结束后3天内
        if trip.start_date <= invoice.issue_date <= trip.end_date + timedelta(days=3):
            # 计算日期接近度
            days_diff = abs((invoice.issue_date - trip.end_date).days)
            if days_diff == 0:
                confidence += 0.3
                reasons.append("发票日期与行程结束日期相同")
            elif days_diff <= 2:
                confidence += 0.2
                reasons.append(f"发票日期在行程结束后{days_diff}天")
            else:
                confidence += 0.1
                reasons.append(f"发票日期在行程范围内")

    # 3. 住宿天数匹配（可选验证）
    if invoice.days and trip.days:
        # 住宿天数应接近行程天数（通常住宿天数=行程天数-1）
        expected_days = trip.days - 1
        if invoice.days == expected_days:
            confidence += 0.1
            reasons.append(f"住宿天数匹配: {invoice.days}天")
        elif invoice.days <= trip.days:
            confidence += 0.05
            reasons.append(f"住宿天数合理: {invoice.days}天")

    reason_str = "; ".join(reasons) if reasons else "无明确匹配依据"
    return confidence, reason_str


def calculate_expenses(trips: List[Trip], invoices: List[HotelInvoice], daily_meal_rate: float = 100.0) -> ExpenseSummary:
    """
    Calculate expenses for all trips.

    Logic:
    1. 对于每个酒店发票，计算与所有行程的匹置信度
    2. 选择匹置信度最高的行程进行匹配
    3. 防止同一发票被多个行程匹配
    4. 返回匹配结果详情供用户确认
    """
    summary = ExpenseSummary()

    # 全局已匹配发票集合（防止重复匹配）
    matched_invoice_ids: Set[str] = set()
    hotel_match_results: List[Dict] = []

    # 为每个行程创建TripExpense
    trip_expenses_dict: Dict[int, TripExpense] = {}
    for i, trip in enumerate(trips):
        trip_expenses_dict[i + 1] = TripExpense(
            trip_id=i + 1,
            trip=trip,
            daily_meal_rate=daily_meal_rate
        )

    # 对每个酒店发票进行智能匹配
    for invoice in invoices:
        invoice_id = invoice.invoice_number or invoice.file_path

        # 已匹配的发票跳过
        if invoice_id in matched_invoice_ids:
            continue

        # 计算与所有行程的匹置信度
        best_trip_id: Optional[int] = None
        best_confidence = 0.0
        best_reason = ""

        for trip_id, trip_expense in trip_expenses_dict.items():
            trip = trip_expense.trip
            confidence, reason = match_hotel_to_trip(trip, invoice)

            if confidence > best_confidence:
                best_confidence = confidence
                best_trip_id = trip_id
                best_reason = reason

        # 只匹配置信度超过阈值(0.3)的发票
        if best_trip_id is not None and best_confidence >= 0.3:
            trip_expenses_dict[best_trip_id].hotel_invoices.append(invoice)
            matched_invoice_ids.add(invoice_id)

            hotel_match_results.append({
                'invoice_id': invoice_id,
                'hotel_name': invoice.hotel_name,
                'matched_trip_id': best_trip_id,
                'confidence': best_confidence,
                'reason': best_reason,
                'total': invoice.total
            })
        else:
            # 未匹配的发票也记录下来
            hotel_match_results.append({
                'invoice_id': invoice_id,
                'hotel_name': invoice.hotel_name,
                'matched_trip_id': None,
                'confidence': best_confidence,
                'reason': f"置信度过低({best_confidence:.2f})，未匹配",
                'total': invoice.total
            })

    # 计算各行程费用
    for trip_id, trip_expense in trip_expenses_dict.items():
        trip_expense.calculate()
        summary.trip_expenses.append(trip_expense)

    summary.hotel_match_results = hotel_match_results
    summary.calculate()
    return summary


def get_expense_breakdown(expense: TripExpense) -> Dict:
    """Get detailed breakdown of expenses for a trip."""
    # 获取返程终点城市
    end_city = ''
    if expense.trip.return_ticket:
        end_city = expense.trip.return_ticket.arrival_station

    return {
        'trip_id': expense.trip_id,
        'trip': {
            'departure_city': expense.trip.departure_city,
            'arrival_city': expense.trip.arrival_city,
            'destination_city': expense.trip.destination_city,
            'end_city': end_city,
            'trip_type': expense.trip.trip_type,
            'trip_dates': f"{expense.trip.start_date.strftime('%Y-%m-%d')} - {expense.trip.end_date.strftime('%Y-%m-%d')}" if expense.trip.start_date and expense.trip.end_date else '',
            'days': expense.trip.days,
            'ticket_total': expense.trip.ticket_total,
            'refund_total': expense.trip.refund_total,
        },
        'departure': expense.trip.departure_city,
        'destination': expense.trip.destination_city or expense.trip.arrival_city,
        'end_city': end_city,
        'trip_type': expense.trip.trip_type,
        'trip_dates': f"{expense.trip.start_date.strftime('%Y-%m-%d')} - {expense.trip.end_date.strftime('%Y-%m-%d')}" if expense.trip.start_date and expense.trip.end_date else '',
        'days': expense.trip.days,
        'tickets': {
            'outbound': {
                'train': expense.trip.outbound_ticket.train_number if expense.trip.outbound_ticket else '',
                'price': expense.trip.outbound_ticket.price if expense.trip.outbound_ticket else 0
            },
            'return': {
                'train': expense.trip.return_ticket.train_number if expense.trip.return_ticket else '',
                'price': expense.trip.return_ticket.price if expense.trip.return_ticket else 0
            },
            'subtotal': expense.trip.ticket_total
        },
        'refunds': {
            'total': expense.trip.refund_total,
            'details': [
                {'train': t.train_number, 'price': t.price} for t in expense.trip.refund_tickets
            ]
        },
        'hotels': {
            'total': expense.hotel_total,
            'details': [
                {'name': inv.hotel_name, 'days': inv.days, 'amount': inv.total} for inv in expense.hotel_invoices
            ]
        },
        'meal_allowance': {
            'days': expense.trip.days,
            'rate': expense.daily_meal_rate,
            'total': expense.meal_allowance
        },
        'grand_total': expense.grand_total
    }