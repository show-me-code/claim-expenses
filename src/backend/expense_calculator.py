"""
Expense Calculator Module - Calculate total expenses for trips.
"""
from datetime import datetime, timedelta
from typing import List, Dict, Set
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

    def calculate(self):
        """Calculate grand totals."""
        self.total_tickets = sum(te.trip.ticket_total for te in self.trip_expenses)
        self.total_refunds = sum(te.trip.refund_total for te in self.trip_expenses)
        self.total_hotels = sum(te.hotel_total for te in self.trip_expenses)
        self.total_meals = sum(te.meal_allowance for te in self.trip_expenses)
        self.grand_total = sum(te.grand_total for te in self.trip_expenses)


def calculate_expenses(trips: List[Trip], invoices: List[HotelInvoice], daily_meal_rate: float = 100.0) -> ExpenseSummary:
    """
    Calculate expenses for all trips.

    Logic:
    1. For each trip, find hotel invoices within the trip date range
    2. Calculate meal allowance based on trip duration
    3. Sum all expenses
    """
    summary = ExpenseSummary()

    for i, trip in enumerate(trips):
        trip_expense = TripExpense(
            trip_id=i + 1,
            trip=trip,
            daily_meal_rate=daily_meal_rate
        )

        # Find hotel invoices matching this trip's date range
        # 使用集合防止同一发票被多个行程重复匹配
        matched_invoice_ids = set()
        if trip.start_date and trip.end_date:
            for invoice in invoices:
                # 防止重复匹配：检查发票是否已被其他行程使用
                invoice_id = invoice.invoice_number or invoice.file_path
                if invoice_id in matched_invoice_ids:
                    continue

                # Hotel invoice date should be within trip range
                # Or invoice issue date should be close to trip end
                if trip.start_date <= invoice.issue_date <= trip.end_date + timedelta(days=3):
                    # Check if hotel is in the destination city
                    dest_city = get_city_base(trip.arrival_city)
                    hotel_city = get_city_base(invoice.hotel_name) if invoice.hotel_name else ''

                    # 城市：酒店名包含城市名（如"南京黄埔大酒店"包含"南京"）
                    if dest_city and hotel_city and dest_city in hotel_city:
                        trip_expense.hotel_invoices.append(invoice)
                        matched_invoice_ids.add(invoice_id)
                    elif dest_city and invoice.hotel_name and dest_city in invoice.hotel_name:
                        trip_expense.hotel_invoices.append(invoice)
                        matched_invoice_ids.add(invoice_id)

        trip_expense.calculate()
        summary.trip_expenses.append(trip_expense)

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


