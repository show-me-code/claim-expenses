"""
Trip Matcher Module - Match outbound and return train tickets to form trips.
支持多种闭环模式：
1. Base(用户指定) -> 出差地 -> Base(用户指定) - 标准闭环
2. 休假地 -> 出差地 -> Base(用户指定) - 休假期间出差
3. Base -> 目的地1 -> 目的地2 -> ... -> Base - 多段行程

Base城市可由用户指定或系统自动推荐
"""
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

from .pdf_parser import TrainTicket


@dataclass
class Trip:
    """A complete trip with outbound and return tickets."""
    outbound_ticket: TrainTicket
    return_ticket: Optional[TrainTicket] = None
    intermediate_tickets: List[TrainTicket] = field(default_factory=list)  # 多段行程中间票据
    refund_tickets: List[TrainTicket] = field(default_factory=list)
    start_date: datetime = None
    end_date: datetime = None
    days: int = 0
    departure_city: str = ""
    arrival_city: str = ""
    destination_city: str = ""  # 出差目的地（第一个）
    destinations: List[str] = field(default_factory=list)  # 所有目的地列表
    ticket_total: float = 0.0
    refund_total: float = 0.0
    trip_type: str = "standard"  # standard, vacation, multi_segment

    def __post_init__(self):
        if self.outbound_ticket:
            self.start_date = self.outbound_ticket.date
            self.departure_city = self.outbound_ticket.departure_station
            self.arrival_city = self.outbound_ticket.arrival_station

        if self.return_ticket:
            self.end_date = self.return_ticket.date

        if self.start_date and self.end_date:
            self.days = (self.end_date - self.start_date).days + 1

        # 计算票据总额（包括中间票据）
        self.ticket_total = self.outbound_ticket.price if self.outbound_ticket else 0
        if self.return_ticket:
            self.ticket_total += self.return_ticket.price
        for t in self.intermediate_tickets:
            self.ticket_total += t.price

        self.refund_total = sum(t.price for t in self.refund_tickets)

        # 设置目的地列表
        self.destinations = [self.arrival_city]
        for t in self.intermediate_tickets:
            if t.arrival_station:
                self.destinations.append(t.arrival_station)


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
    2. 休假地 -> 出差地 -> Base（休假期间出差）
    3. Base -> 目的地1 -> 目的地2 -> ... -> Base（多段行程）

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
        matched_trip_data = None

        # 模式1：从Base出发 - 可能是标准闭环或多段行程的起点
        if is_city_in_station(base_city, ticket1.departure_station):
            matched_trip_data = match_from_base(ticket1, normal_tickets, used_tickets, base_city)

        # 模式2：终点是Base - 可能是休假模式或返程票
        elif is_city_in_station(base_city, ticket1.arrival_station):
            matched_trip_data = match_returning_to_base(ticket1, normal_tickets, used_tickets, base_city)

        # 如果没有找到闭环匹配，跳过
        if matched_trip_data is None:
            continue

        outbound, intermediate, return_ticket, trip_type = matched_trip_data

        # 找到匹配的退票（改进：基于票据关联匹配）
        all_dates = [outbound.date]
        for t in intermediate:
            all_dates.append(t.date)
        if return_ticket:
            all_dates.append(return_ticket.date)

        # 收集行程涉及的站点和车次
        trip_stations = set()
        trip_stations.add(get_city_base(outbound.departure_station))
        trip_stations.add(get_city_base(outbound.arrival_station))
        for t in intermediate:
            trip_stations.add(get_city_base(t.departure_station))
            trip_stations.add(get_city_base(t.arrival_station))
        if return_ticket:
            trip_stations.add(get_city_base(return_ticket.departure_station))
            trip_stations.add(get_city_base(return_ticket.arrival_station))

        trip_trains = set()
        trip_trains.add(outbound.train_number)
        for t in intermediate:
            trip_trains.add(t.train_number)
        if return_ticket:
            trip_trains.add(return_ticket.train_number)

        matched_refunds = []
        start_date = min(all_dates)
        end_date = max(all_dates)

        for refund in refund_tickets:
            if refund.file_path not in used_tickets:
                # 优先级1：车次号匹配
                refund_train = refund.train_number
                if refund_train and refund_train in trip_trains:
                    matched_refunds.append(refund)
                    used_tickets.add(refund.file_path)
                    continue

                # 优先级2：站点匹配（退票涉及的站点在行程站点中）
                refund_dep = get_city_base(refund.departure_station)
                refund_arr = get_city_base(refund.arrival_station)
                if refund_dep in trip_stations or refund_arr in trip_stations:
                    matched_refunds.append(refund)
                    used_tickets.add(refund.file_path)
                    continue

                # 优先级3：日期范围匹配（作为fallback）
                if start_date <= refund.date <= end_date:
                    matched_refunds.append(refund)
                    used_tickets.add(refund.file_path)

        # 创建行程
        trip = Trip(
            outbound_ticket=outbound,
            return_ticket=return_ticket,
            intermediate_tickets=intermediate,
            refund_tickets=matched_refunds,
            trip_type=trip_type
        )

        # 设置出差目的地
        trip.destination_city = outbound.arrival_station

        trips.append(trip)

        # 标记已使用
        used_tickets.add(outbound.file_path)
        for t in intermediate:
            used_tickets.add(t.file_path)
        if return_ticket:
            used_tickets.add(return_ticket.file_path)

    return trips


def match_from_base(start_ticket: TrainTicket, all_tickets: List[TrainTicket],
                    used_tickets: set, base_city: str) -> Optional[Tuple]:
    """
    从Base出发的票据匹配逻辑
    支持标准闭环和多段行程

    Returns:
        (outbound, intermediate_tickets, return_ticket, trip_type) or None
    """
    intermediate_tickets = []
    current_ticket = start_ticket
    current_city = current_ticket.arrival_station

    # 寻找后续票据链
    for next_ticket in all_tickets:
        if next_ticket.file_path in used_tickets:
            continue
        if next_ticket.file_path == current_ticket.file_path:
            continue
        if next_ticket.date < current_ticket.date:
            continue

        # 检查是否是下一段行程
        if city_similarity(next_ticket.departure_station, current_city):
            # 检查是否回到Base（返程）
            if is_city_in_station(base_city, next_ticket.arrival_station):
                # 找到返程，形成闭环
                return (start_ticket, intermediate_tickets, next_ticket,
                        "standard" if not intermediate_tickets else "multi_segment")
            else:
                # 继续前往下一个目的地
                intermediate_tickets.append(next_ticket)
                current_ticket = next_ticket
                current_city = next_ticket.arrival_station

    return None


def match_returning_to_base(return_ticket: TrainTicket, all_tickets: List[TrainTicket],
                            used_tickets: set, base_city: str) -> Optional[Tuple]:
    """
    返回Base的票据匹配逻辑
    支持休假期间出差模式

    Returns:
        (outbound, intermediate_tickets, return_ticket, trip_type) or None
    """
    # 从返程票反向追溯行程链
    intermediate_tickets = []
    current_ticket = return_ticket
    current_city = return_ticket.departure_station  # 这是出差地

    # 反向寻找票据
    for prev_ticket in all_tickets:
        if prev_ticket.file_path in used_tickets:
            continue
        if prev_ticket.file_path == current_ticket.file_path:
            continue
        if prev_ticket.date > current_ticket.date:
            continue

        # 检查是否是前一段行程
        if city_similarity(prev_ticket.arrival_station, current_city):
            # 检查出发地
            if is_city_in_station(base_city, prev_ticket.departure_station):
                # 找到从Base出发的去程，标准闭环
                return (prev_ticket, intermediate_tickets, return_ticket,
                        "vacation" if intermediate_tickets else "standard")
            else:
                # 继续反向追溯（休假地出发）
                intermediate_tickets.insert(0, prev_ticket)
                current_ticket = prev_ticket
                current_city = prev_ticket.departure_station

    # 如果追溯到非Base出发，形成休假期间出差闭环
    if intermediate_tickets:
        outbound = intermediate_tickets[0]
        rest_intermediate = intermediate_tickets[1:]
        return (outbound, rest_intermediate, return_ticket, "vacation")

    return None


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

    # 格式化目的地列表
    destinations_str = ' → '.join(trip.destinations) if trip.destinations else trip.arrival_city

    # 获取中间车次
    intermediate_trains = [t.train_number for t in trip.intermediate_tickets]

    return {
        'departure_city': trip.departure_city,
        'arrival_city': trip.arrival_city,
        'destination_city': trip.destination_city,
        'destinations': trip.destinations,  # 所有目的地列表
        'destinations_str': destinations_str,  # 格式化的目的地字符串
        'end_city': end_city,
        'start_date': trip.start_date.strftime('%Y-%m-%d') if trip.start_date else '',
        'end_date': trip.end_date.strftime('%Y-%m-%d') if trip.end_date else '',
        'trip_dates': trip_dates,
        'days': trip.days,
        'outbound_train': trip.outbound_ticket.train_number if trip.outbound_ticket else '',
        'intermediate_trains': intermediate_trains,
        'return_train': trip.return_ticket.train_number if trip.return_ticket else '',
        'ticket_total': trip.ticket_total,
        'refund_total': trip.refund_total,
        'trip_type': trip.trip_type,
        'segment_count': len(trip.intermediate_tickets) + 2 if trip.return_ticket else len(trip.intermediate_tickets) + 1,
        'files': [
            trip.outbound_ticket.file_path if trip.outbound_ticket else '',
            *[t.file_path for t in trip.intermediate_tickets],
            trip.return_ticket.file_path if trip.return_ticket else '',
            *[t.file_path for t in trip.refund_tickets]
        ]
    }