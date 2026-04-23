"""
Expense Claim System - Backend Entry Point
"""
from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS
import os
import sys
import json
import uuid
import shutil
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

app = Flask(__name__, static_folder='../frontend')
CORS(app)

# Configuration
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '..', '..', 'uploads')
OUTPUT_FOLDER = os.path.join(os.path.dirname(__file__), '..', '..', 'output')
PROCESSED_RECORD_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'processed_invoices.json')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Upload sessions storage (in-memory for simplicity)
upload_sessions = {}  # session_id -> {folder_path, folder_name, created_at}


@app.route('/', methods=['GET'])
def index():
    """Serve frontend page."""
    return send_from_directory(app.static_folder, 'index.html')


@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok', 'message': 'Expense Claim System is running'})


@app.route('/api/upload', methods=['POST'])
def upload_files():
    """
    接收上传的PDF文件，保存到临时文件夹
    返回session_id用于后续处理
    """
    try:
        files = request.files.getlist('files')
        if not files:
            return jsonify({'error': 'No files uploaded'}), 400

        # Generate session ID
        session_id = str(uuid.uuid4())[:8]

        # Get folder name from first file's relative path
        first_file = files[0]
        relative_path = first_file.filename  # e.g., "folder_name/subfolder/file.pdf"
        folder_name = relative_path.split('/')[0] if '/' in relative_path else 'uploaded_files'

        # Create session folder
        session_folder = os.path.join(UPLOAD_FOLDER, f'session_{session_id}')
        os.makedirs(session_folder, exist_ok=True)

        # Save all files, preserving folder structure
        saved_count = 0
        for file in files:
            relative_path = file.filename
            # Extract subfolder and filename
            parts = relative_path.split('/')
            if len(parts) > 1:
                # Create subfolder structure
                subfolder = os.path.join(session_folder, *parts[:-1])
                os.makedirs(subfolder, exist_ok=True)
                file_path = os.path.join(subfolder, parts[-1])
            else:
                file_path = os.path.join(session_folder, parts[0])

            file.save(file_path)
            saved_count += 1

        # Store session info
        upload_sessions[session_id] = {
            'folder_path': session_folder,
            'folder_name': folder_name,
            'created_at': datetime.now(),
            'file_count': saved_count
        }

        return jsonify({
            'success': True,
            'session_id': session_id,
            'folder_name': folder_name,
            'file_count': saved_count
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/base-cities', methods=['GET'])
def get_base_cities():
    """获取常用Base城市列表（用于下拉选择）"""
    from backend.trip_matcher import COMMON_BASE_CITIES
    return jsonify({
        'success': True,
        'cities': COMMON_BASE_CITIES
    })


@app.route('/api/detect-base', methods=['POST'])
def detect_base_city():
    """
    自动检测Base城市和出差目的地
    从票据中分析最频繁出现的出发城市作为Base
    """
    from backend.pdf_parser import parse_all_pdfs
    from backend.trip_matcher import detect_base_city, detect_destination_cities

    data = request.get_json(force=True)
    root_folder = data.get('rootFolder')

    if not root_folder:
        return jsonify({'error': 'Root folder path is required'}), 400

    try:
        # 解析所有票据（不跳过已处理的，用于分析）
        tickets, _ = parse_all_pdfs(root_folder, skip_processed=False)

        if not tickets:
            return jsonify({
                'success': True,
                'detected_base': '北京',
                'destinations': [],
                'message': '没有找到票据，使用默认Base城市'
            })

        # 自动检测Base城市
        detected_base = detect_base_city(tickets)

        # 检测出差目的地
        destinations = detect_destination_cities(tickets, detected_base)

        return jsonify({
            'success': True,
            'detected_base': detected_base,
            'destinations': destinations,
            'ticket_count': len(tickets)
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/process', methods=['POST', 'OPTIONS'])
def process_expenses():
    """Process PDF files and generate expense summary."""
    # Handle CORS preflight
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'}), 200

    from backend.pdf_parser import parse_all_pdfs, load_processed_records
    from backend.trip_matcher import match_trips, get_trip_summary
    from backend.expense_calculator import calculate_expenses, get_expense_breakdown
    from backend.file_organizer import organize_files
    from backend.excel_generator import generate_excel

    # Get JSON data
    try:
        data = request.get_json(force=True)
    except Exception as e:
        return jsonify({'error': f'JSON parse error: {str(e)}'}), 400

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    root_folder = data.get('rootFolder')
    session_id = data.get('sessionId')  # 从上传会话获取文件夹路径
    daily_meal_rate = data.get('dailyMealRate', 100)
    skip_processed = data.get('skipProcessed', True)  # 默认跳过已处理的发票
    base_city = data.get('baseCity')  # 用户指定或自动检测的Base城市

    # 如果提供了session_id，使用上传的文件夹
    if session_id and session_id in upload_sessions:
        root_folder = upload_sessions[session_id]['folder_path']

    if not root_folder:
        return jsonify({'error': 'Root folder path or sessionId is required'}), 400

    try:
        # 获取当前已处理记录（用于返回给前端显示）
        processed_before = load_processed_records()

        # Step 1: Parse all PDFs (with skip_processed option)
        tickets, invoices = parse_all_pdfs(root_folder, skip_processed=skip_processed)

        # 检查是否有新票据
        if not tickets and not invoices:
            return jsonify({
                'success': True,
                'message': '没有发现新的票据（所有发票可能已处理过）',
                'trips': [],
                'expenses': {
                    'trip_expenses': [],
                    'total_tickets': 0,
                    'total_refunds': 0,
                    'total_hotels': 0,
                    'total_meals': 0,
                    'grand_total': 0
                },
                'processed_count': {
                    'tickets': len(processed_before.get('tickets', [])),
                    'invoices': len(processed_before.get('invoices', []))
                }
            })

        # Step 2: Match trips (outbound + return) with optional base_city
        trips = match_trips(tickets, base_city=base_city)

        # Step 3: Calculate expenses
        expenses = calculate_expenses(trips, invoices, daily_meal_rate)

        # Step 4: Organize files into folders
        organized_folders = organize_files(root_folder, trips, expenses)

        # Step 5: Generate Excel
        excel_path = generate_excel(expenses, OUTPUT_FOLDER)

        # 获取更新后的已处理记录
        processed_after = load_processed_records()

        # Convert to JSON-serializable format
        trips_json = [get_trip_summary(t) for t in trips]
        expenses_json = {
            'trip_expenses': [get_expense_breakdown(te) for te in expenses.trip_expenses],
            'total_tickets': expenses.total_tickets,
            'total_refunds': expenses.total_refunds,
            'total_hotels': expenses.total_hotels,
            'total_meals': expenses.total_meals,
            'grand_total': expenses.grand_total
        }

        return jsonify({
            'success': True,
            'trips': trips_json,
            'expenses': expenses_json,
            'organized_folders': organized_folders,
            'excel_path': excel_path,
            'processed_count': {
                'tickets': len(processed_after.get('tickets', [])),
                'invoices': len(processed_after.get('invoices', [])),
                'new_tickets': len(tickets),
                'new_invoices': len(invoices)
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/processed', methods=['GET'])
def get_processed_records():
    """获取已处理的发票记录列表"""
    try:
        if os.path.exists(PROCESSED_RECORD_FILE):
            with open(PROCESSED_RECORD_FILE, 'r', encoding='utf-8') as f:
                records = json.load(f)
            return jsonify({
                'success': True,
                'tickets': records.get('tickets', []),
                'invoices': records.get('invoices', []),
                'ticket_count': len(records.get('tickets', [])),
                'invoice_count': len(records.get('invoices', []))
            })
        return jsonify({
            'success': True,
            'tickets': [],
            'invoices': [],
            'ticket_count': 0,
            'invoice_count': 0
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/clear', methods=['POST'])
def clear_processed_records():
    """清除已处理的发票记录（允许重新计算）"""
    try:
        from backend.pdf_parser import clear_processed_records
        clear_processed_records()
        return jsonify({
            'success': True,
            'message': '已清除所有处理记录，可以重新计算所有发票'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/download/<filename>', methods=['GET'])
def download_file(filename):
    """Download generated Excel file."""
    file_path = os.path.join(OUTPUT_FOLDER, filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    return jsonify({'error': 'File not found'}), 404


if __name__ == '__main__':
    app.run(debug=True, port=5000)