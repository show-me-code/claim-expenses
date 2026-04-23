"""
File Organizer Module - Organize PDF files into trip folders.
"""
import os
import shutil
from datetime import datetime
from typing import List, Dict

from .trip_matcher import Trip
from .expense_calculator import TripExpense


def organize_files(root_folder: str, trips: List[Trip], expenses) -> List[str]:
    """
    Organize PDF files into folders based on trip dates.

    Creates folder structure:
    YYYY-MM-DD-YYYY-MM-DD/
        [dep] ticket.pdf
        [ret] ticket.pdf
        [sup] refund.pdf
        hotel_invoice.pdf
        summary.txt
    """
    organized_folders = []

    for trip_expense in expenses.trip_expenses:
        trip = trip_expense.trip

        if not trip.start_date:
            continue

        # Create folder name based on dates
        start_str = trip.start_date.strftime('%Y-%m-%d')
        end_str = trip.end_date.strftime('%Y-%m-%d') if trip.end_date else start_str
        folder_name = f"{start_str}-{end_str}"

        # Create folder in root
        folder_path = os.path.join(root_folder, folder_name)
        os.makedirs(folder_path, exist_ok=True)

        # Copy outbound ticket
        if trip.outbound_ticket and trip.outbound_ticket.file_path:
            src = trip.outbound_ticket.file_path
            dst = os.path.join(folder_path, f"[dep] {os.path.basename(src)}")
            if os.path.exists(src) and not os.path.exists(dst):
                shutil.copy2(src, dst)

        # Copy return ticket
        if trip.return_ticket and trip.return_ticket.file_path:
            src = trip.return_ticket.file_path
            dst = os.path.join(folder_path, f"[ret] {os.path.basename(src)}")
            if os.path.exists(src) and not os.path.exists(dst):
                shutil.copy2(src, dst)

        # Copy refund tickets
        for refund in trip.refund_tickets:
            if refund.file_path:
                src = refund.file_path
                dst = os.path.join(folder_path, f"[sup] {os.path.basename(src)}")
                if os.path.exists(src) and not os.path.exists(dst):
                    shutil.copy2(src, dst)

        # Copy hotel invoices
        for invoice in trip_expense.hotel_invoices:
            if invoice.file_path:
                src = invoice.file_path
                # Clean up filename
                base_name = os.path.basename(src)
                dst = os.path.join(folder_path, base_name)
                if os.path.exists(src) and not os.path.exists(dst):
                    shutil.copy2(src, dst)

        # Create summary.txt
        summary_content = generate_folder_summary(trip, trip_expense)
        summary_path = os.path.join(folder_path, 'summary.txt')
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write(summary_content)

        organized_folders.append(folder_path)

    return organized_folders


def generate_folder_summary(trip: Trip, expense: TripExpense) -> str:
    """Generate summary text content for a trip folder."""
    lines = [
        "差旅费用汇总",
        "=" * 50,
        "",
        f"出差日期: {trip.start_date.strftime('%Y-%m-%d')} - {trip.end_date.strftime('%Y-%m-%d') if trip.end_date else '待确认'}",
        f"出差天数: {trip.days} 天",
        f"出发地: {trip.departure_city}",
        f"目的地: {trip.arrival_city}",
        "",
        "【交通费】",
        f"  去程: {trip.outbound_ticket.train_number if trip.outbound_ticket else ''} - ￥{trip.outbound_ticket.price if trip.outbound_ticket else 0:.2f}",
        f"  返程: {trip.return_ticket.train_number if trip.return_ticket else ''} - ￥{trip.return_ticket.price if trip.return_ticket else 0:.2f}",
        f"  退票费: ￥{trip.refund_total:.2f}",
        f"  小计: ￥{trip.ticket_total + trip.refund_total:.2f}",
        "",
        "【住宿费】",
    ]

    for inv in expense.hotel_invoices:
        lines.append(f"  {inv.hotel_name} ({inv.days}天) - ￥{inv.total:.2f}")
    lines.append(f"  小计: ￥{expense.hotel_total:.2f}")

    lines.extend([
        "",
        "【伙食补助】",
        f"  {trip.days}天 × ￥{expense.daily_meal_rate:.2f}/天 = ￥{expense.meal_allowance:.2f}",
        "",
        "=" * 50,
        f"总计: ￥{expense.grand_total:.2f}",
    ])

    return '\n'.join(lines)