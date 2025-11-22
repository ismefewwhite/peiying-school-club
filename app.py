import os
from datetime import datetime
from io import BytesIO
from flask import Flask, render_template_string, request, redirect, url_for, flash, send_file
from flask_sqlalchemy import SQLAlchemy
import pandas as pd

# 初始化 Flask 應用程式
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here'  # 用於 Session 和 Flash 訊息
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///school_clubs.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ==========================================
# 1. 資料庫模型 (Database Models)
# ==========================================

class Club(db.Model):
    """社團資料表"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)  # 儲存 HTML 內容 (圖片/表格)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    max_regular = db.Column(db.Integer, default=20)   # 正取名額
    max_waitlist = db.Column(db.Integer, default=5)   # 備取名額
    
    # 建立關聯，方便查詢該社團的所有報名者
    registrations = db.relationship('Registration', backref='club', cascade="all, delete-orphan")

    def current_regular_count(self):
        return Registration.query.filter_by(club_id=self.id, status='正取').count()

    def current_waitlist_count(self):
        return Registration.query.filter_by(club_id=self.id, status='備取').count()

class Registration(db.Model):
    """報名資料表"""
    id = db.Column(db.Integer, primary_key=True)
    club_id = db.Column(db.Integer, db.ForeignKey('club.id'), nullable=False)
    student_name = db.Column(db.String(50), nullable=False)
    student_class = db.Column(db.String(20), nullable=False) # 班級座號
    parent_phone = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(10), nullable=False)  # '正取' 或 '備取'
    created_at = db.Column(db.DateTime, default=datetime.now)

# ==========================================
# 2. HTML 模板 (Templates)
# 為了方便單一檔案執行，將 HTML 寫在字串中
# 實際專案建議放在 templates/ 資料夾
# ==========================================

BASE_LAYOUT = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>國小社團報名系統</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #f8f9fa; font-family: "Microsoft JhengHei", sans-serif; }
        .container { margin-top: 30px; }
        .card { margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        .status-badge { font-size: 0.9em; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
        <div class="container-fluid">
            <a class="navbar-brand" href="/">🏫 社團報名首頁</a>
            <div class="d-flex">
                <a href="/admin" class="btn btn-warning btn-sm">⚙️ 管理者後台</a>
            </div>
        </div>
    </nav>
    
    <div class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}
            {% for category, message in messages %}
              <div class="alert alert-{{ category }}">{{ message }}</div>
            {% endfor %}
          {% endif %}
        {% endwith %}
        
        {% block content %}{% endblock %}
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script src="https://cdn.ckeditor.com/ckeditor5/39.0.1/classic/ckeditor.js"></script>
</body>
</html>
"""

HOME_TEMPLATE = BASE_LAYOUT.replace("{% block content %}{% endblock %}", """
<h2 class="mb-4">目前開放報名的社團</h2>
<div class="row">
    {% for club in clubs %}
    <div class="col-md-6 col-lg-4">
        <div class="card h-100">
            <div class="card-body">
                <h5 class="card-title">{{ club.name }}</h5>
                <p class="card-text text-muted">
                    報名時間：<br>
                    {{ club.start_time.strftime('%Y-%m-%d %H:%M') }} ~ <br>
                    {{ club.end_time.strftime('%Y-%m-%d %H:%M') }}
                </p>
                <ul class="list-group list-group-flush mb-3">
                    <li class="list-group-item d-flex justify-content-between align-items-center">
                        正取名額
                        <span class="badge bg-success rounded-pill">{{ club.current_regular_count() }} / {{ club.max_regular }}</span>
                    </li>
                    <li class="list-group-item d-flex justify-content-between align-items-center">
                        備取名額
                        <span class="badge bg-secondary rounded-pill">{{ club.current_waitlist_count() }} / {{ club.max_waitlist }}</span>
                    </li>
                </ul>
                <a href="/club/{{ club.id }}" class="btn btn-primary w-100">查看詳情與報名</a>
            </div>
        </div>
    </div>
    {% else %}
    <div class="col-12"><p>目前沒有開放的社團。</p></div>
    {% endfor %}
</div>
""")

CLUB_DETAIL_TEMPLATE = BASE_LAYOUT.replace("{% block content %}{% endblock %}", """
<div class="row">
    <div class="col-md-8">
        <div class="card">
            <div class="card-header bg-white">
                <h3>{{ club.name }}</h3>
            </div>
            <div class="card-body">
                <!-- 顯示富文本內容 (圖片/表格) -->
                <div class="club-description">
                    {{ club.description | safe }}
                </div>
            </div>
        </div>
    </div>
    <div class="col-md-4">
        <div class="card">
            <div class="card-header bg-info text-white">學生報名</div>
            <div class="card-body">
                {% if can_register %}
                    <form action="/register/{{ club.id }}" method="POST">
                        <div class="mb-3">
                            <label class="form-label">學生姓名</label>
                            <input type="text" name="student_name" class="form-control" required>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">班級座號 (例: 60105)</label>
                            <input type="text" name="student_class" class="form-control" required>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">家長聯絡電話</label>
                            <input type="tel" name="parent_phone" class="form-control" required>
                        </div>
                        <button type="submit" class="btn btn-success w-100">確認報名</button>
                    </form>
                {% else %}
                    <div class="alert alert-warning text-center">
                        {{ status_message }}
                    </div>
                {% endif %}
            </div>
        </div>
    </div>
</div>
""")

ADMIN_DASHBOARD_TEMPLATE = BASE_LAYOUT.replace("{% block content %}{% endblock %}", """
<div class="d-flex justify-content-between align-items-center mb-4">
    <h2>管理者後台</h2>
    <a href="/admin/create" class="btn btn-success">+ 新增社團</a>
</div>
<table class="table table-striped bg-white">
    <thead>
        <tr>
            <th>社團名稱</th>
            <th>報名狀況 (正取/備取)</th>
            <th>功能</th>
        </tr>
    </thead>
    <tbody>
        {% for club in clubs %}
        <tr>
            <td>{{ club.name }}</td>
            <td>
                <span class="text-success">{{ club.current_regular_count() }}/{{ club.max_regular }}</span> | 
                <span class="text-secondary">{{ club.current_waitlist_count() }}/{{ club.max_waitlist }}</span>
            </td>
            <td>
                <a href="/admin/export/{{ club.id }}" class="btn btn-sm btn-success">匯出 Excel</a>
                <a href="/admin/delete/{{ club.id }}" class="btn btn-sm btn-danger" onclick="return confirm('確定刪除？')">刪除</a>
            </td>
        </tr>
        {% endfor %}
    </tbody>
</table>
""")

ADMIN_CREATE_TEMPLATE = BASE_LAYOUT.replace("{% block content %}{% endblock %}", """
<h2 class="mb-4">新增社團</h2>
<form action="/admin/create" method="POST">
    <div class="row">
        <div class="col-md-6 mb-3">
            <label class="form-label">社團名稱</label>
            <input type="text" name="name" class="form-control" required>
        </div>
        <div class="col-md-3 mb-3">
            <label class="form-label">正取名額</label>
            <input type="number" name="max_regular" class="form-control" value="20" required>
        </div>
        <div class="col-md-3 mb-3">
            <label class="form-label">備取名額</label>
            <input type="number" name="max_waitlist" class="form-control" value="5" required>
        </div>
    </div>
    <div class="row">
        <div class="col-md-6 mb-3">
            <label class="form-label">開始報名時間</label>
            <input type="datetime-local" name="start_time" class="form-control" required>
        </div>
        <div class="col-md-6 mb-3">
            <label class="form-label">結束報名時間</label>
            <input type="datetime-local" name="end_time" class="form-control" required>
        </div>
    </div>
    <div class="mb-3">
        <label class="form-label">詳細介紹 (可貼上圖片、表格)</label>
        <textarea name="description" id="editor"></textarea>
    </div>
    <button type="submit" class="btn btn-primary">發布社團</button>
    <a href="/admin" class="btn btn-secondary">取消</a>
</form>

<script>
    ClassicEditor
        .create( document.querySelector( '#editor' ) )
        .catch( error => {
            console.error( error );
        } );
</script>
<style>
.ck-editor__editable_inline {
    min-height: 300px;
}
</style>
""")

# ==========================================
# 3. 路由與核心邏輯 (Routes & Logic)
# ==========================================

@app.route('/')
def index():
    clubs = Club.query.order_by(Club.start_time.desc()).all()
    return render_template_string(HOME_TEMPLATE, clubs=clubs)

@app.route('/club/<int:club_id>')
def club_detail(club_id):
    club = Club.query.get_or_404(club_id)
    now = datetime.now()
    
    can_register = True
    status_message = ""

    # 檢查時間
    if now < club.start_time:
        can_register = False
        status_message = "報名尚未開始"
    elif now > club.end_time:
        can_register = False
        status_message = "報名已截止"
    else:
        # 檢查名額 (如果正取和備取都滿了)
        reg_count = club.current_regular_count()
        wait_count = club.current_waitlist_count()
        if reg_count >= club.max_regular and wait_count >= club.max_waitlist:
            can_register = False
            status_message = "名額已額滿"

    return render_template_string(CLUB_DETAIL_TEMPLATE, club=club, can_register=can_register, status_message=status_message)

@app.route('/register/<int:club_id>', methods=['POST'])
def register_student(club_id):
    """
    核心報名邏輯：處理正取與備取判定
    """
    club = Club.query.get_or_404(club_id)
    now = datetime.now()

    # 1. 伺服器端再次驗證時間
    if not (club.start_time <= now <= club.end_time):
        flash('不在報名時間範圍內，報名失敗。', 'danger')
        return redirect(url_for('club_detail', club_id=club_id))

    student_name = request.form.get('student_name')
    student_class = request.form.get('student_class')
    parent_phone = request.form.get('parent_phone')

    # 2. 簡單驗證重複報名 (可選功能，這裡以班級+姓名判斷)
    existing = Registration.query.filter_by(club_id=club_id, student_class=student_class, student_name=student_name).first()
    if existing:
        flash('您已經報名過此社團了！', 'warning')
        return redirect(url_for('club_detail', club_id=club_id))

    # 3. 判定 正取/備取/額滿 (使用 Transaction 鎖定檢查建議使用更進階資料庫，SQLite 這裡做簡易示範)
    status = None
    
    current_reg = club.current_regular_count()
    current_wait = club.current_waitlist_count()

    if current_reg < club.max_regular:
        status = '正取'
        flash(f'報名成功！恭喜 {student_name} 為【正取】。', 'success')
    elif current_wait < club.max_waitlist:
        status = '備取'
        flash(f'報名成功，但目前正取已滿。{student_name} 列為【備取第 {current_wait + 1} 順位】。', 'warning')
    else:
        flash('很抱歉，本社團已全數額滿。', 'danger')
        return redirect(url_for('club_detail', club_id=club_id))

    # 4. 寫入資料庫
    new_reg = Registration(
        club_id=club.id,
        student_name=student_name,
        student_class=student_class,
        parent_phone=parent_phone,
        status=status
    )
    db.session.add(new_reg)
    db.session.commit()

    return redirect(url_for('club_detail', club_id=club_id))

# --- 管理者路由 ---

@app.route('/admin')
def admin_dashboard():
    clubs = Club.query.all()
    return render_template_string(ADMIN_DASHBOARD_TEMPLATE, clubs=clubs)

@app.route('/admin/create', methods=['GET', 'POST'])
def admin_create():
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description') # 包含 HTML
        start_time = datetime.strptime(request.form.get('start_time'), '%Y-%m-%dT%H:%M')
        end_time = datetime.strptime(request.form.get('end_time'), '%Y-%m-%dT%H:%M')
        max_regular = int(request.form.get('max_regular'))
        max_waitlist = int(request.form.get('max_waitlist'))

        new_club = Club(
            name=name, description=description,
            start_time=start_time, end_time=end_time,
            max_regular=max_regular, max_waitlist=max_waitlist
        )
        db.session.add(new_club)
        db.session.commit()
        flash('社團新增成功！', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template_string(ADMIN_CREATE_TEMPLATE)

@app.route('/admin/delete/<int:club_id>')
def admin_delete(club_id):
    club = Club.query.get_or_404(club_id)
    db.session.delete(club)
    db.session.commit()
    flash('社團已刪除', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/export/<int:club_id>')
def admin_export(club_id):
    """
    匯出 Excel 功能
    """
    club = Club.query.get_or_404(club_id)
    regs = Registration.query.filter_by(club_id=club_id).all()

    # 將資料轉為 Dictionary 列表
    data = []
    for r in regs:
        data.append({
            "班級座號": r.student_class,
            "學生姓名": r.student_name,
            "家長電話": r.parent_phone,
            "報名狀態": r.status,
            "報名時間": r.created_at.strftime('%Y-%m-%d %H:%M:%S')
        })

    # 轉為 Pandas DataFrame
    df = pd.DataFrame(data)
    
    # 寫入記憶體中的 Excel 檔案
    output = BytesIO()
    # 使用 openpyxl 作為引擎
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='報名名單')
    
    output.seek(0)
    
    filename = f"{club.name}_報名名單.xlsx"
    return send_file(output, as_attachment=True, download_name=filename)

# 應用程式啟動點
if __name__ == '__main__':
    with app.app_context():
        db.create_all() # 自動建立資料庫
        print("資料庫已初始化。請開啟 http://127.0.0.1:5000 進行測試")
    app.run(debug=True)