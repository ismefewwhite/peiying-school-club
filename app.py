import os
from datetime import datetime, time
from io import BytesIO
from functools import wraps
from flask import Flask, render_template_string, request, redirect, url_for, flash, send_file, session
from flask_sqlalchemy import SQLAlchemy
import pandas as pd

# 初始化 Flask 應用程式
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///school_clubs.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- 設定管理者帳號密碼 (您可以修改這裡) ---
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'password123' 

db = SQLAlchemy(app)

# ==========================================
# 1. 資料庫模型 (Database Models)
# ==========================================

class SystemConfig(db.Model):
    """系統設定：存首頁標題、圖片等"""
    id = db.Column(db.Integer, primary_key=True)
    site_title = db.Column(db.String(100), default="國小社團報名系統")
    welcome_msg = db.Column(db.Text, default="歡迎各位同學參加社團活動！")
    banner_image = db.Column(db.String(500), nullable=True) # 圖片網址

class Club(db.Model):
    """社團資料表"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    # 報名時間限制
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    # 名額限制
    max_regular = db.Column(db.Integer, default=20)
    max_waitlist = db.Column(db.Integer, default=5)
    # --- 新增：上課時間設定 ---
    weekday = db.Column(db.String(10), nullable=False) # 例如 "星期一"
    class_start = db.Column(db.Time, nullable=False)   # 例如 16:00
    class_end = db.Column(db.Time, nullable=False)     # 例如 17:30
    
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
    student_class = db.Column(db.String(20), nullable=False)
    parent_phone = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(10), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

# ==========================================
# 2. 輔助功能 (Helpers)
# ==========================================

# 登入檢查裝飾器
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('請先登入管理者帳號', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_system_config():
    """取得系統設定，如果沒有就自動建立預設值"""
    conf = SystemConfig.query.first()
    if not conf:
        conf = SystemConfig()
        db.session.add(conf)
        db.session.commit()
    return conf

# ==========================================
# 3. HTML 模板
# ==========================================

BASE_LAYOUT = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ config.site_title }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #f8f9fa; font-family: "Microsoft JhengHei", sans-serif; }
        .container { margin-top: 30px; margin-bottom: 50px; }
        .card { margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        .club-img { height: 200px; object-fit: cover; background-color: #eee; }
        .banner-area { 
            background-color: #e9ecef; padding: 2rem; margin-bottom: 2rem; border-radius: .3rem; 
            text-align: center;
        }
        .banner-img { max-width: 100%; max-height: 300px; margin-top: 15px; border-radius: 5px; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
        <div class="container-fluid">
            <a class="navbar-brand" href="/">🏫 {{ config.site_title }}</a>
            <div class="d-flex">
                {% if session.get('logged_in') %}
                    <a href="/admin" class="btn btn-warning btn-sm me-2">⚙️ 管理後台</a>
                    <a href="/logout" class="btn btn-outline-light btn-sm">登出</a>
                {% else %}
                    <a href="/login" class="btn btn-outline-light btn-sm">管理者登入</a>
                {% endif %}
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

LOGIN_TEMPLATE = BASE_LAYOUT.replace("{% block content %}{% endblock %}", """
<div class="row justify-content-center">
    <div class="col-md-4">
        <div class="card">
            <div class="card-header bg-primary text-white">管理者登入</div>
            <div class="card-body">
                <form method="POST">
                    <div class="mb-3">
                        <label>帳號</label>
                        <input type="text" name="username" class="form-control" required>
                    </div>
                    <div class="mb-3">
                        <label>密碼</label>
                        <input type="password" name="password" class="form-control" required>
                    </div>
                    <button type="submit" class="btn btn-primary w-100">登入</button>
                </form>
            </div>
        </div>
    </div>
</div>
""")

HOME_TEMPLATE = BASE_LAYOUT.replace("{% block content %}{% endblock %}", """
<div class="banner-area">
    <h1 class="display-5">{{ config.site_title }}</h1>
    <p class="lead">{{ config.welcome_msg | safe }}</p>
    {% if config.banner_image %}
        <img src="{{ config.banner_image }}" class="banner-img">
    {% endif %}
</div>

<h3 class="mb-3 border-start border-5 border-primary ps-2">目前開放報名的社團</h3>
<div class="row">
    {% for club in clubs %}
    <div class="col-md-6 col-lg-4">
        <div class="card h-100">
            <div class="card-body">
                <h5 class="card-title fw-bold">{{ club.name }}</h5>
                <span class="badge bg-info text-dark mb-2">
                    {{ club.weekday }} {{ club.class_start.strftime('%H:%M') }}-{{ club.class_end.strftime('%H:%M') }}
                </span>
                <p class="card-text mt-2 text-muted small">
                    報名期限：{{ club.end_time.strftime('%m/%d %H:%M') }} 截止
                </p>
                <div class="d-flex justify-content-between text-center mb-3 border p-2 rounded bg-light">
                    <div>
                        <div class="fw-bold text-success">{{ club.current_regular_count() }}/{{ club.max_regular }}</div>
                        <small>正取</small>
                    </div>
                    <div>
                        <div class="fw-bold text-secondary">{{ club.current_waitlist_count() }}/{{ club.max_waitlist }}</div>
                        <small>備取</small>
                    </div>
                </div>
                <a href="/club/{{ club.id }}" class="btn btn-primary w-100">查看詳情與報名</a>
            </div>
        </div>
    </div>
    {% else %}
    <div class="col-12 text-center py-5 text-muted">目前沒有開放的社團。</div>
    {% endfor %}
</div>
""")

CLUB_DETAIL_TEMPLATE = BASE_LAYOUT.replace("{% block content %}{% endblock %}", """
<div class="row">
    <div class="col-md-8">
        <div class="card h-100">
            <div class="card-header bg-white d-flex justify-content-between align-items-center">
                <h3 class="m-0">{{ club.name }}</h3>
                <span class="badge bg-primary fs-6">
                    {{ club.weekday }} {{ club.class_start.strftime('%H:%M') }} ~ {{ club.class_end.strftime('%H:%M') }}
                </span>
            </div>
            <div class="card-body">
                <div class="club-description">
                    {{ club.description | safe }}
                </div>
            </div>
        </div>
    </div>
    <div class="col-md-4">
        <div class="card">
            <div class="card-header bg-info text-white fw-bold">學生報名表</div>
            <div class="card-body">
                {% if can_register %}
                    <div class="alert alert-light border mb-3 small">
                        請確認上課時間不會與其他社團衝突。
                    </div>
                    <form action="/register/{{ club.id }}" method="POST">
                        <div class="mb-3">
                            <label class="form-label">學生姓名</label>
                            <input type="text" name="student_name" class="form-control" required placeholder="例如：王小明">
                        </div>
                        <div class="mb-3">
                            <label class="form-label">班級座號</label>
                            <input type="text" name="student_class" class="form-control" required placeholder="例如：60105">
                        </div>
                        <div class="mb-3">
                            <label class="form-label">家長聯絡電話</label>
                            <input type="tel" name="parent_phone" class="form-control" required>
                        </div>
                        <button type="submit" class="btn btn-success w-100 py-2 fw-bold">確認報名</button>
                    </form>
                {% else %}
                    <div class="alert alert-warning text-center">
                        <h4>🔒 無法報名</h4>
                        <p>{{ status_message }}</p>
                    </div>
                {% endif %}
            </div>
        </div>
    </div>
</div>
""")

ADMIN_DASHBOARD_TEMPLATE = BASE_LAYOUT.replace("{% block content %}{% endblock %}", """
<div class="d-flex justify-content-between align-items-center mb-4">
    <h2>⚙️ 管理者後台</h2>
    <div>
        <a href="/admin/config" class="btn btn-info me-2">🏠 編輯首頁設定</a>
        <a href="/admin/create" class="btn btn-success">+ 新增社團</a>
    </div>
</div>
<table class="table table-hover bg-white shadow-sm rounded">
    <thead class="table-dark">
        <tr>
            <th>社團名稱</th>
            <th>上課時間</th>
            <th>報名狀況 (正/備)</th>
            <th>功能</th>
        </tr>
    </thead>
    <tbody>
        {% for club in clubs %}
        <tr>
            <td>{{ club.name }}</td>
            <td>{{ club.weekday }} {{ club.class_start.strftime('%H:%M') }}</td>
            <td>
                <span class="text-success fw-bold">{{ club.current_regular_count() }}/{{ club.max_regular }}</span> | 
                <span class="text-secondary">{{ club.current_waitlist_count() }}/{{ club.max_waitlist }}</span>
            </td>
            <td>
                <a href="/admin/export/{{ club.id }}" class="btn btn-sm btn-outline-success">📥 匯出名單</a>
                <a href="/admin/delete/{{ club.id }}" class="btn btn-sm btn-outline-danger" onclick="return confirm('確定刪除？資料無法復原喔！')">🗑️ 刪除</a>
            </td>
        </tr>
        {% endfor %}
    </tbody>
</table>
""")

ADMIN_CONFIG_TEMPLATE = BASE_LAYOUT.replace("{% block content %}{% endblock %}", """
<h2 class="mb-4">🏠 編輯首頁與網站設定</h2>
<form method="POST" class="card p-4">
    <div class="mb-3">
        <label class="form-label">網站標題</label>
        <input type="text" name="site_title" class="form-control" value="{{ config.site_title }}" required>
    </div>
    <div class="mb-3">
        <label class="form-label">首頁圖片網址 (Banner Image URL)</label>
        <input type="text" name="banner_image" class="form-control" value="{{ config.banner_image or '' }}" placeholder="請貼上圖片連結，例如 https://example.com/image.jpg">
        <div class="form-text">建議先將圖片上傳到 Imgur 或學校網站，再貼上網址。</div>
    </div>
    <div class="mb-3">
        <label class="form-label">首頁歡迎詞 (支援 HTML/圖片)</label>
        <textarea name="welcome_msg" id="editor">{{ config.welcome_msg }}</textarea>
    </div>
    <button type="submit" class="btn btn-primary">儲存設定</button>
    <a href="/admin" class="btn btn-secondary">返回</a>
</form>
<script>
    ClassicEditor.create(document.querySelector('#editor')).catch(error => console.error(error));
</script>
""")

ADMIN_CREATE_TEMPLATE = BASE_LAYOUT.replace("{% block content %}{% endblock %}", """
<h2 class="mb-4">新增社團</h2>
<form action="/admin/create" method="POST" class="card p-4">
    <div class="row">
        <div class="col-md-6 mb-3">
            <label class="form-label">社團名稱</label>
            <input type="text" name="name" class="form-control" required placeholder="例如：週一樂高社">
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

    <h5 class="mt-3 text-primary border-bottom pb-2">🕒 上課時段設定 (用於衝堂檢查)</h5>
    <div class="row bg-light p-3 rounded mb-3">
        <div class="col-md-4 mb-3">
            <label class="form-label">上課日</label>
            <select name="weekday" class="form-select" required>
                <option value="星期一">星期一</option>
                <option value="星期二">星期二</option>
                <option value="星期三">星期三</option>
                <option value="星期四">星期四</option>
                <option value="星期五">星期五</option>
                <option value="星期六">星期六</option>
                <option value="星期日">星期日</option>
            </select>
        </div>
        <div class="col-md-4 mb-3">
            <label class="form-label">上課開始時間</label>
            <input type="time" name="class_start" class="form-control" required>
        </div>
        <div class="col-md-4 mb-3">
            <label class="form-label">上課結束時間</label>
            <input type="time" name="class_end" class="form-control" required>
        </div>
    </div>

    <h5 class="mt-3 text-primary border-bottom pb-2">📅 報名期間設定</h5>
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
    <button type="submit" class="btn btn-primary btn-lg">發布社團</button>
    <a href="/admin" class="btn btn-secondary btn-lg">取消</a>
</form>

<script>
    ClassicEditor.create(document.querySelector('#editor')).catch(error => console.error(error));
</script>
<style> .ck-editor__editable_inline { min-height: 300px; } </style>
""")

# ==========================================
# 4. 路由與核心邏輯
# ==========================================

@app.context_processor
def inject_config():
    """讓所有頁面都能讀取系統設定"""
    return dict(config=get_system_config())

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['username'] == ADMIN_USERNAME and request.form['password'] == ADMIN_PASSWORD:
            session['logged_in'] = True
            flash('登入成功！', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('帳號或密碼錯誤', 'danger')
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('已登出', 'info')
    return redirect(url_for('index'))

@app.route('/')
def index():
    clubs = Club.query.order_by(Club.weekday, Club.class_start).all()
    return render_template_string(HOME_TEMPLATE, clubs=clubs)

@app.route('/club/<int:club_id>')
def club_detail(club_id):
    club = Club.query.get_or_404(club_id)
    now = datetime.now()
    
    can_register = True
    status_message = ""

    if now < club.start_time:
        can_register = False
        status_message = f"報名尚未開始 (開放時間：{club.start_time.strftime('%m/%d %H:%M')})"
    elif now > club.end_time:
        can_register = False
        status_message = "報名已截止"
    else:
        reg_count = club.current_regular_count()
        wait_count = club.current_waitlist_count()
        if reg_count >= club.max_regular and wait_count >= club.max_waitlist:
            can_register = False
            status_message = "名額已額滿"

    return render_template_string(CLUB_DETAIL_TEMPLATE, club=club, can_register=can_register, status_message=status_message)

@app.route('/register/<int:club_id>', methods=['POST'])
def register_student(club_id):
    club = Club.query.get_or_404(club_id)
    now = datetime.now()

    if not (club.start_time <= now <= club.end_time):
        flash('不在報名時間範圍內，報名失敗。', 'danger')
        return redirect(url_for('club_detail', club_id=club_id))

    student_name = request.form.get('student_name')
    student_class = request.form.get('student_class')
    parent_phone = request.form.get('parent_phone')

    # --- 1. 檢查是否重複報名同一個社團 ---
    existing = Registration.query.filter_by(club_id=club_id, student_class=student_class).first()
    if existing:
        flash('您已經報名過此社團了！', 'warning')
        return redirect(url_for('club_detail', club_id=club_id))

    # --- 2. 衝堂檢查 (Time Conflict Check) ---
    # 找出該學生已報名的所有社團 (且狀態不是取消)
    student_regs = Registration.query.filter_by(student_class=student_class).all()
    for reg in student_regs:
        existing_club = reg.club
        # 如果星期相同
        if existing_club.weekday == club.weekday:
            # 檢查時間是否有重疊
            # 邏輯：(新開始 < 舊結束) AND (新結束 > 舊開始) 代表有重疊
            if (club.class_start < existing_club.class_end) and (club.class_end > existing_club.class_start):
                flash(f'❌ 報名失敗！與已報名的【{existing_club.name}】上課時間衝突。', 'danger')
                return redirect(url_for('club_detail', club_id=club_id))

    # --- 3. 正取/備取判定 ---
    status = None
    current_reg = club.current_regular_count()
    current_wait = club.current_waitlist_count()

    if current_reg < club.max_regular:
        status = '正取'
        flash(f'✅ 報名成功！恭喜 {student_name} 為【正取】。', 'success')
    elif current_wait < club.max_waitlist:
        status = '備取'
        flash(f'⚠️ 報名成功，但正取已滿。{student_name} 列為【備取第 {current_wait + 1} 順位】。', 'warning')
    else:
        flash('❌ 很抱歉，本社團已全數額滿。', 'danger')
        return redirect(url_for('club_detail', club_id=club_id))

    new_reg = Registration(
        club_id=club.id, student_name=student_name,
        student_class=student_class, parent_phone=parent_phone, status=status
    )
    db.session.add(new_reg)
    db.session.commit()

    return redirect(url_for('club_detail', club_id=club_id))

# --- 管理者路由 ---

@app.route('/admin')
@login_required
def admin_dashboard():
    clubs = Club.query.all()
    return render_template_string(ADMIN_DASHBOARD_TEMPLATE, clubs=clubs)

@app.route('/admin/config', methods=['GET', 'POST'])
@login_required
def admin_config():
    conf = get_system_config()
    if request.method == 'POST':
        conf.site_title = request.form.get('site_title')
        conf.welcome_msg = request.form.get('welcome_msg')
        conf.banner_image = request.form.get('banner_image')
        db.session.commit()
        flash('網站設定已更新', 'success')
        return redirect(url_for('admin_config'))
    return render_template_string(ADMIN_CONFIG_TEMPLATE)

@app.route('/admin/create', methods=['GET', 'POST'])
@login_required
def admin_create():
    if request.method == 'POST':
        try:
            # 時間處理
            c_start = datetime.strptime(request.form.get('class_start'), '%H:%M').time()
            c_end = datetime.strptime(request.form.get('class_end'), '%H:%M').time()
            
            new_club = Club(
                name=request.form.get('name'),
                description=request.form.get('description'),
                start_time=datetime.strptime(request.form.get('start_time'), '%Y-%m-%dT%H:%M'),
                end_time=datetime.strptime(request.form.get('end_time'), '%Y-%m-%dT%H:%M'),
                max_regular=int(request.form.get('max_regular')),
                max_waitlist=int(request.form.get('max_waitlist')),
                weekday=request.form.get('weekday'),
                class_start=c_start,
                class_end=c_end
            )
            db.session.add(new_club)
            db.session.commit()
            flash('社團新增成功！', 'success')
            return redirect(url_for('admin_dashboard'))
        except Exception as e:
            flash(f'新增失敗，請檢查欄位格式: {str(e)}', 'danger')

    return render_template_string(ADMIN_CREATE_TEMPLATE)

@app.route('/admin/delete/<int:club_id>')
@login_required
def admin_delete(club_id):
    club = Club.query.get_or_404(club_id)
    db.session.delete(club)
    db.session.commit()
    flash('社團已刪除', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/export/<int:club_id>')
@login_required
def admin_export(club_id):
    club = Club.query.get_or_404(club_id)
    regs = Registration.query.filter_by(club_id=club_id).all()
    data = []
    for r in regs:
        data.append({
            "班級座號": r.student_class,
            "學生姓名": r.student_name,
            "家長電話": r.parent_phone,
            "報名狀態": r.status,
            "報名時間": r.created_at.strftime('%Y-%m-%d %H:%M:%S')
        })
    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='報名名單')
    output.seek(0)
    return send_file(output, as_attachment=True, download_name=f"{club.name}_名單.xlsx")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # 初始化系統設定
        get_system_config()
    app.run(debug=True)
