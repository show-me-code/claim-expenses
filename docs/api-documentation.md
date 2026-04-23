# API接口文档

## 基础信息

- **Base URL**: `http://localhost:5000/api`
- **Content-Type**: `application/json`
- **字符编码**: UTF-8

## 接口列表

### 健康检查

```
GET /api/health
```

响应：
```json
{
    "status": "ok",
    "message": "Expense Claim System is running"
}
```

### 处理发票

```
POST /api/process
```

请求参数：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| rootFolder | string | 是 | 发票文件夹路径 |
| dailyMealRate | number | 否 | 伙食补助标准（默认100） |
| skipProcessed | boolean | 否 | 是否跳过已处理（默认true） |
| baseCity | string | 否 | Base城市名称（如"北京"），不填则自动检测 |

请求示例：
```json
{
    "rootFolder": "你的发票文件夹路径",
    "dailyMealRate": 100,
    "skipProcessed": true,
    "baseCity": "北京"
}
```

响应：
```json
{
    "success": true,
    "trips": [
        {
            "trip_id": 1,
            "departure_city": "北京南站",
            "destination_city": "南京南站",
            "trip_dates": "2026-01-25 - 2026-01-30",
            "days": 6,
            "trip_type": "standard",
            "ticket_total": 997.0,
            "refund_total": 106.5
        }
    ],
    "expenses": {
        "trip_expenses": [...],
        "total_tickets": 997.0,
        "total_refunds": 106.5,
        "total_hotels": 1900.0,
        "total_meals": 600.0,
        "grand_total": 3603.5
    },
    "processed_count": {
        "tickets": 3,
        "invoices": 1,
        "new_tickets": 3,
        "new_invoices": 1
    },
    "excel_path": "output/差旅费用汇总_xxx.xlsx"
}
```

错误响应：
```json
{
    "error": "错误信息"
}
```

### 获取已处理记录

```
GET /api/processed
```

响应：
```json
{
    "success": true,
    "ticket_count": 3,
    "invoice_count": 1,
    "tickets": ["发票号码1", "发票号码2", ...],
    "invoices": ["发票号码1", ...]
}
```

### 清除已处理记录

```
POST /api/clear
```

响应：
```json
{
    "success": true,
    "message": "已清除所有处理记录"
}
```

### 获取Base城市列表

```
GET /api/base-cities
```

响应：
```json
{
    "success": true,
    "cities": ["北京", "上海", "广州", "深圳", "成都", "杭州", "南京", "武汉", "西安", "重庆", "天津", "苏州", "长沙", "郑州", "青岛"]
}
```

### 自动检测Base城市

```
POST /api/detect-base
```

请求参数：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| rootFolder | string | 是 | 发票文件夹路径 |

响应：
```json
{
    "success": true,
    "detected_base": "北京",
    "destinations": ["南京", "上海"],
    "ticket_count": 5
}
```

### 下载Excel

```
GET /api/download/<filename>
```

返回Excel文件二进制流。

## 错误码

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 参数错误（缺少rootFolder等） |
| 500 | 服务器内部错误 |

## 使用示例

### Python

```python
import requests

# 处理发票
response = requests.post('http://localhost:5000/api/process', json={
    'rootFolder': 'C:/Users/你的用户名/Documents/发票文件夹',
    'dailyMealRate': 100
})

if response.status_code == 200:
    data = response.json()
    print(f'总金额: {data["expenses"]["grand_total"]}')
else:
    print(f'错误: {response.json()["error"]}')
```

### JavaScript

```javascript
fetch('http://localhost:5000/api/process', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        rootFolder: '你的发票文件夹路径',
        dailyMealRate: 100
    })
})
.then(res => res.json())
.then(data => {
    console.log('总金额:', data.expenses.grand_total);
})
.catch(err => console.error('错误:', err));
```