"""
Trip Matcher Module - Match outbound and return train tickets to form trips.
支持多种闭环模式：
1. Base(用户指定) -> 出差地 -> Base(用户指定) - 标准闭环
2. 休假地 -> 出差地 -> Base(用户指定) - 休假期间出差

Base城市可由用户指定或系统自动推荐
"""
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass, field

from .pdf_parser import TrainTicket


@dataclass
class Trip:
    """A complete trip with outbound and return tickets."""
    outbound_ticket: TrainTicket
    return_ticket: Optional[TrainTicket] = None
    refund_tickets: List[TrainTicket] = field(default_factory=list)
    start_date: datetime = None
    end_date: datetime = None
    days: int = 0
    departure_city: str = ""
    arrival_city: str = ""
    destination_city: str = ""  # 出差目的地
    ticket_total: float = 0.0
    refund_total: float = 0.0
    trip_type: str = "standard"  # standard: Base->出差地->Base, vacation: 休假地->出差地->Base

    def __post_init__(self):
        if self.outbound_ticket:
            self.start_date = self.outbound_ticket.date
            self.departure_city = self.outbound_ticket.departure_station
            self.arrival_city = self.outbound_ticket.arrival_station

        if self.return_ticket:
            self.end_date = self.return_ticket.date

        if self.start_date and self.end_date:
            self.days = (self.end_date - self.start_date).days + 1

        self.ticket_total = self.outbound_ticket.price if self.outbound_ticket else 0
        if self.return_ticket:
            self.ticket_total += self.return_ticket.price

        self.refund_total = sum(t.price for t in self.refund_tickets)


# 常见Base城市列表（用于下拉推荐）
COMMON_BASE_CITIES = [
    '北京',
    '上海',
    '广州',
    '深圳',
    '成都',
    '杭州',
    '南京',
    '武汉',
    '西安',
    '重庆',
    '天津',
    '苏州',
    '长沙',
    '郑州',
    '青岛',
]


def get_city_base(station: str) -> str:
    """获取城市基础名称（去掉南站/站等后缀）"""
    return station.replace('南站', '').replace('北站', '').replace('东站', '').replace('西站', '').replace('站', '')


def city_similarity(city1: str, city2: str) -> bool:
    """Check if two city names are similar (handle variations)."""
    city1_base = get_city_base(city1)
    city2_base = get_city_base(city2)
    return city1_base == city2_base or city1_base in city2_base or city2_base in city1_base


def is_city_in_station(city: str, station: str) -> bool:
    """检查城市名是否在站名中"""
    return city in station or get_city_base(station) == city


def detect_base_city(tickets: List[TrainTicket]) -> str:
    """
    自动检测Base城市（最频繁出现的出发城市）
    返回推荐的城市名
    """
    city_count = {}

    for ticket in tickets:
        city = get_city_base(ticket.departure_station)
        if city:
            city_count[city] = city_count.get(city, 0) + 1

        city = get_city_base(ticket.arrival_station)
        if city:
            city_count[city] = city_count.get(city, 0) + 1

    if not city_count:
        return COMMON_BASE_CITIES[0]  # 默认北京

    # 返回出现次数最多的城市
    return max(city_count, key=city_count.get)


def detect_destination_cities(tickets: List[TrainTicket], base_city: str) -> List[str]:
    """
    检测出差目的地城市列表
    返回所有非Base的城市
    """
    destinations = set()

    for ticket in tickets:
        dep_city = get_city_base(ticket.departure_station)
        arr_city = get_city_base(ticket.arrival_station)

        # 出发不是Base，到达可能是出差地
        if dep_city != base_city and not is_city_in_station(base_city, ticket.departure_station):
            destinations.add(dep_city)

        # 到达不是Base，可能是出差地
        if arr_city != base_city and not is_city_in_station(base_city, ticket.arrival_station):
            destinations.add(arr_city)

    return sorted(list(destinations))


def match_trips(tickets: List[TrainTicket], base_city: str = None) -> List[Trip]:
    """
    Match train tickets to form complete trips.

    Args:
        tickets: 票据列表
        base_city: Base城市名称（如"北京"），如果为None则自动检测

    支持的闭环模式：
    1. Base -> 出差地 -> Base（标准闭环）
       - 去程：出发=Base，终点=出差地
       - 返程：出发=出差地，终点=Base

    2. 休假地 -> 出差地 -> Base（休假期间出差）
       - 去程：出发=休假地（非Base），终点=出差地
       - 返程：出发=出差地，终点=Base

    注意：只返回闭环行程（有去程和返程），不闭环的票不计入
    """
    # 如果没有指定base，自动检测
    if not base_city:
        base_city = detect_base_city(tickets)

    # 分类票据：退票单独处理
    normal_tickets = [t for t in tickets if t.ticket_type != 'refund']
    refund_tickets = [t for t in tickets if t.ticket_type == 'refund']

    # 按日期排序
    normal_tickets.sort(key=lambda t: t.date)
    refund_tickets.sort(key=lambda t: t.date)

    trips = []
    used_tickets = set()  # 已使用的票据（防止重复匹配）

    for i, ticket1 in enumerate(normal_tickets):
        if ticket1.file_path in used_tickets:
            continue

        # 尝试匹配闭环
        matched_ticket = None
        trip_type = "standard"

        # 模式1：Base -> 出差地 -> Base
        # ticket1是去程（Base出发），找返程（终点Base）
        if is_city_in_station(base_city, ticket1.departure_station):
            destination = ticket1.arrival_station
            for ticket2 in normal_tickets:
                if ticket2.file_path in used_tickets or ticket2.file_path == ticket1.file_path:
                    continue
                # 返程：从出差地出发，回到Base
                if is_city_in_station(base_city, ticket2.arrival_station) and \
                   city_similarity(ticket2.departure_station, destination) and \
                   ticket2.date >= ticket1.date:
                    matched_ticket = ticket2
                    trip_type = "standard"
                    break

        # 模式2：休假地 -> 出差地 -> Base
        # ticket1是去程（休假地出发），找返程（终点Base）
        elif is_city_in_station(base_city, ticket1.arrival_station):
            # ticket1终点是Base，这可能是返程票
            # 需要找到对应的去程票
            destination = ticket1.departure_station  # 出差地
            for ticket2 in normal_tickets:
                if ticket2.file_path in used_tickets or ticket2.file_path == ticket1.file_path:
                    continue
                # 去程：终点是出差地，出发不是Base
                if city_similarity(ticket2.arrival_station, destination) and \
                   not is_city_in_station(base_city, ticket2.departure_station) and \
                   ticket2.date <= ticket1.date:
                    matched_ticket = ticket2
                    trip_type = "vacation_return"  # 这是返程票匹配去程
                    break

        # 如果没有找到闭环匹配，跳过（不闭环不计入）
        if matched_ticket is None:
            continue

        # 找到匹配的退票
        matched_refunds = []
        start_date = min(ticket1.date, matched_ticket.date)
        end_date = max(ticket1.date, matched_ticket.date)

        for refund in refund_tickets:
            if refund.file_path not in used_tickets:
                if start_date <= refund.date <= end_date:
                    matched_refunds.append(refund)
                    used_tickets.add(refund.file_path)

        # 创建行程
        if trip_type == "standard":
            # ticket1是去程，matched_ticket是返程
            outbound = ticket1
            return_ticket = matched_ticket
        elif trip_type == "vacation_return":
            # matched_ticket是去程，ticket1是返程
            outbound = matched_ticket
            return_ticket = ticket1
            trip_type = "vacation"  # 修正类型

        trip = Trip(
            outbound_ticket=outbound,
            return_ticket=return_ticket,
            refund_tickets=matched_refunds,
            trip_type=trip_type
        )

        # 设置出差目的地
        trip.destination_city = outbound.arrival_station

        trips.append(trip)

        # 标记已使用
        used_tickets.add(ticket1.file_path)
        used_tickets.add(matched_ticket.file_path)

    return trips


def get_trip_summary(trip: Trip) -> Dict:
    """Generate a summary dictionary for a trip."""
    # 获取返程终点城市（闭环终点）
    end_city = ''
    if trip.return_ticket:
        end_city = trip.return_ticket.arrival_station

    # 格式化日期范围
    trip_dates = ''
    if trip.start_date and trip.end_date:
        trip_dates = f"{trip.start_date.strftime('%Y-%m-%d')} - {trip.end_date.strftime('%Y-%m-%d')}"

    return {
        'departure_city': trip.departure_city,
        'arrival_city': trip.arrival_city,
        'destination_city': trip.destination_city,
        'end_city': end_city,  # 返程终点（闭环终点）
        'start_date': trip.start_date.strftime('%Y-%m-%d') if trip.start_date else '',
        'end_date': trip.end_date.strftime('%Y-%m-%d') if trip.end_date else '',
        'trip_dates': trip_dates,
        'days': trip.days,
        'outbound_train': trip.outbound_ticket.train_number if trip.outbound_ticket else '',
        'return_train': trip.return_ticket.train_number if trip.return_ticket else '',
        'ticket_total': trip.ticket_total,
        'refund_total': trip.refund_total,
        'trip_type': trip.trip_type,
        'files': [
            trip.outbound_ticket.file_path if trip.outbound_ticket else '',
            trip.return_ticket.file_path if trip.return_ticket else '',
            *[t.file_path for t in trip.refund_tickets]
        ]
    }