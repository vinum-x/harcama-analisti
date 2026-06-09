from flask import Flask, render_template, request, jsonify  # type: ignore
import json
import os
from datetime import datetime, timedelta
from typing import Any, List, Dict
import google.generativeai as genai  # type: ignore
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

DATA_FILE = os.path.join(os.path.dirname(__file__), 'data', 'expenses.json')

CATEGORIES = {
    "market": {"label": "Market", "icon": '<i class="bi bi-basket2-fill"></i>'},
    "yemek": {"label": "Yemek", "icon": '<i class="bi bi-fork-knife"></i>'},
    "ulasim": {"label": "Ulaşım", "icon": '<i class="bi bi-car-front-fill"></i>'},
    "kozmetik": {"label": "Kozmetik", "icon": '<i class="bi bi-magic"></i>'},
    "eglence": {"label": "Eğlence", "icon": '<i class="bi bi-controller"></i>'},
    "egitim": {"label": "Eğitim", "icon": '<i class="bi bi-book"></i>'},
    "abonelik": {"label": "Abonelik", "icon": '<i class="bi bi-credit-card-fill"></i>'},
    "online": {"label": "Online Alışveriş", "icon": '<i class="bi bi-bag-fill"></i>'},
    "diger": {"label": "Diğer", "icon": '<i class="bi bi-three-dots"></i>'}
}


def load_expenses() -> List[Dict[str, Any]]:
    """JSON dosyasından harcamaları yükle"""
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data: List[Dict[str, Any]] = json.load(f)
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_expenses(expenses):
    """Harcamaları JSON dosyasına kaydet"""
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(expenses, f, ensure_ascii=False, indent=2)


@app.route('/')
def index():
    return render_template('index.html', categories=CATEGORIES)


@app.route('/api/categories', methods=['GET'])
def get_categories():
    return jsonify(CATEGORIES)


@app.route('/api/expenses', methods=['GET'])
def get_expenses():
    """Harcamaları getir - filtreleme ve sayfalama destekli"""
    expenses = load_expenses()

    # Filtreleme
    category = request.args.get('category', '')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    start_time = request.args.get('start_time', '')
    end_time = request.args.get('end_time', '')
    period = request.args.get('period', '')  # weekly, monthly

    filtered = expenses.copy()

    if category:
        filtered = [e for e in filtered if e.get('category') == category]

    if start_date:
        filtered = [e for e in filtered if e.get('date', '') >= start_date]

    if end_date:
        filtered = [e for e in filtered if e.get('date', '') <= end_date]

    if start_time:
        filtered = [e for e in filtered if e.get('time', '') >= start_time]

    if end_time:
        filtered = [e for e in filtered if e.get('time', '') <= end_time]

    if period == 'weekly':
        today = datetime.now()
        week_start = today - timedelta(days=today.weekday())
        week_start_str = week_start.strftime('%Y-%m-%d')
        filtered = [e for e in filtered if e.get('date', '') >= week_start_str]
    elif period == 'monthly':
        today = datetime.now()
        month_start_str = today.strftime('%Y-%m-01')
        filtered = [e for e in filtered if e.get('date', '') >= month_start_str]

    # Tarihe göre sırala (en yeni en üstte)
    filtered.sort(key=lambda x: (x.get('date', ''), x.get('time', '')), reverse=True)

    # Sayfalama
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 10))
    total = len(filtered)
    total_pages = max(1, (total + per_page - 1) // per_page)
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated: List[Dict[str, Any]] = filtered[start_idx:end_idx]  # type: ignore[arg-type]

    return jsonify({
        'expenses': paginated,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': total_pages
    })


@app.route('/api/expenses', methods=['POST'])
def add_expense():
    """Yeni harcama ekle"""
    data = request.get_json()

    if not data:
        return jsonify({'error': 'Veri bulunamadı'}), 400

    required_fields = ['category', 'amount', 'date', 'time']
    for field in required_fields:
        if field not in data or not data[field]:
            return jsonify({'error': f'{field} alanı zorunludur'}), 400

    try:
        amount = float(data['amount'])
        if amount <= 0:
            return jsonify({'error': 'Tutar pozitif olmalıdır'}), 400
    except (ValueError, TypeError):
        return jsonify({'error': 'Geçersiz tutar'}), 400

    expenses = load_expenses()

    expense = {
        'id': len(expenses) + 1 if not expenses else max(e.get('id', 0) for e in expenses) + 1,
        'name': data.get('name', ''),
        'category': data['category'],
        'amount': amount,
        'date': data['date'],
        'time': data['time'],
        'description': data.get('description', ''),
        'created_at': datetime.now().isoformat()
    }

    expenses.append(expense)
    save_expenses(expenses)

    return jsonify({'message': 'Harcama başarıyla eklendi', 'expense': expense}), 201


@app.route('/api/expenses/<int:expense_id>', methods=['DELETE'])
def delete_expense(expense_id):
    """Harcamayı sil"""
    expenses = load_expenses()
    expenses = [e for e in expenses if e.get('id') != expense_id]
    save_expenses(expenses)
    return jsonify({'message': 'Harcama silindi'})


@app.route('/api/expenses/<int:expense_id>', methods=['PUT'])
def update_expense(expense_id):
    """Harcamayı güncelle"""
    data = request.get_json()

    if not data:
        return jsonify({'error': 'Veri bulunamadı'}), 400

    expenses = load_expenses()
    expense = next((e for e in expenses if e.get('id') == expense_id), None)

    if not expense:
        return jsonify({'error': 'Harcama bulunamadı'}), 404

    # Güncelle
    if 'category' in data and data['category']:
        expense['category'] = data['category']
    if 'amount' in data:
        try:
            amount = float(data['amount'])
            if amount <= 0:
                return jsonify({'error': 'Tutar pozitif olmalıdır'}), 400
            expense['amount'] = amount
        except (ValueError, TypeError):
            return jsonify({'error': 'Geçersiz tutar'}), 400
    if 'date' in data and data['date']:
        expense['date'] = data['date']
    if 'time' in data and data['time']:
        expense['time'] = data['time']
    if 'name' in data:
        expense['name'] = data['name']
    if 'description' in data:
        expense['description'] = data['description']

    expense['updated_at'] = datetime.now().isoformat()

    save_expenses(expenses)
    return jsonify({'message': 'Harcama güncellendi', 'expense': expense})


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """İstatistikleri getir"""
    expenses = load_expenses()

    if not expenses:
        return jsonify({
            'total_spending': 0,
            'category_totals': {},
            'monthly_totals': {},
            'weekly_totals': {},
            'busiest_day': None,
            'busiest_hour': None,
            'expense_count': 0
        })

    # Toplam harcama
    total_spending = sum(e.get('amount', 0) for e in expenses)

    # Kategori bazlı toplamlar
    category_totals = {}
    for e in expenses:
        cat = e.get('category', 'diger')
        category_totals[cat] = category_totals.get(cat, 0) + e.get('amount', 0)

    # Aylık toplamlar
    monthly_totals = {}
    for e in expenses:
        month = e.get('date', '')[:7]  # YYYY-MM
        if month:
            monthly_totals[month] = monthly_totals.get(month, 0) + e.get('amount', 0)

    # Haftalık toplamlar
    weekly_totals = {}
    for e in expenses:
        try:
            d = datetime.strptime(e.get('date', ''), '%Y-%m-%d')
            week_start = d - timedelta(days=d.weekday())
            week_key = week_start.strftime('%Y-%m-%d')
            weekly_totals[week_key] = weekly_totals.get(week_key, 0) + e.get('amount', 0)
        except (ValueError, TypeError):
            pass

    # En yoğun gün
    day_counts = {}
    for e in expenses:
        day = e.get('date', '')
        if day:
            day_counts[day] = day_counts.get(day, 0) + 1
    busiest_day = max(day_counts, key=lambda k: day_counts[k]) if day_counts else None

    # En yoğun saat aralığı
    hour_counts = {}
    for e in expenses:
        time_str = e.get('time', '')
        if time_str:
            try:
                hour = int(time_str.split(':')[0])
                hour_range = f"{hour:02d}:00-{hour+1:02d}:00"
                hour_counts[hour_range] = hour_counts.get(hour_range, 0) + 1
            except (ValueError, IndexError):
                pass
    busiest_hour = max(hour_counts, key=lambda k: hour_counts[k]) if hour_counts else None

    # En yoğun ay
    month_counts = {}
    for e in expenses:
        month = e.get('date', '')[:7]
        if month:
            month_counts[month] = month_counts.get(month, 0) + 1
    busiest_month = max(month_counts, key=lambda k: month_counts[k]) if month_counts else None

    return jsonify({
        'total_spending': total_spending,
        'category_totals': category_totals,
        'monthly_totals': monthly_totals,
        'weekly_totals': weekly_totals,
        'busiest_day': busiest_day,
        'busiest_hour': busiest_hour,
        'busiest_month': busiest_month,
        'expense_count': len(expenses),
        'day_counts': day_counts,
        'hour_counts': hour_counts,
        'month_counts': month_counts
    })


@app.route('/api/analyze', methods=['POST'])
def analyze_expenses():
    """Google Generative AI ile harcama analizi"""
    data = request.get_json() or {}

    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        return jsonify({'error': 'Sunucuda GEMINI_API_KEY çevresel değişkeni bulunamadı. Lütfen .env dosyanızı kontrol edin.'}), 500

    expenses = load_expenses()

    # Filtreleri uygula
    filtered = expenses.copy()
    start_date = data.get('start_date', '')
    end_date = data.get('end_date', '')
    category = data.get('category', '')
    analysis_type = data.get('analysis_type', 'general')

    if category:
        filtered = [e for e in filtered if e.get('category') == category]
    if start_date:
        filtered = [e for e in filtered if e.get('date', '') >= start_date]
    if end_date:
        filtered = [e for e in filtered if e.get('date', '') <= end_date]

    if not filtered:
        return jsonify({'error': 'Seçilen dönemde harcama bulunamadı'}), 404

    # İstatistikleri hesapla
    total = sum(e.get('amount', 0) for e in filtered)
    cat_totals = {}
    for e in filtered:
        cat = e.get('category', 'diger')
        cat_totals[cat] = cat_totals.get(cat, 0) + e.get('amount', 0)

    # Günlük harcama istatistikleri
    daily_totals = {}
    for e in filtered:
        day = e.get('date', '')
        if day:
            daily_totals[day] = daily_totals.get(day, 0) + e.get('amount', 0)

    avg_daily = total / max(len(daily_totals), 1)

    # Saat bazlı analiz
    hour_spending = {}
    for e in filtered:
        t = e.get('time', '')
        if t:
            try:
                h = int(t.split(':')[0])
                hour_spending[h] = hour_spending.get(h, 0) + e.get('amount', 0)
            except:
                pass

    expense_summary = json.dumps(filtered, ensure_ascii=False, indent=2)

    # Kategori ikonları referansı
    cat_icons = ", ".join([f'"{cat}": {CATEGORIES[cat]["icon"]}' for cat in CATEGORIES])

    # Temel istatistik bilgisi (tüm tipler için ortak)
    base_stats = f"""## Harcama Verileri (JSON):
{expense_summary}

## Özet İstatistikler:
- Toplam Harcama: {total:.2f} TL
- Harcama Sayısı: {len(filtered)} adet
- Günlük Ortalama: {avg_daily:.2f} TL
- Kategori Dağılımı: {json.dumps(cat_totals, ensure_ascii=False)}
- Saat Bazlı Harcama: {json.dumps(hour_spending, ensure_ascii=False)}
- Günlük Toplamlar: {json.dumps(daily_totals, ensure_ascii=False)}"""

    # Format direktifleri (tüm tipler için ortak)
    format_directives = f"""Kategorileri belirtirken mutlaka simgelerini kullan: {cat_icons}

İpuçlarını veya önemli noktaları vurgularken <i class="fa-solid fa-sparkles"></i> kullan. 
Yemekle ilgili ipuçlarında <i class="fa-light fa-sandwich"></i>, harcama notlarında ise <i class="fa-regular fa-music"></i> ikonlarını kullanabilirsin.
Yanıtını TAMAMEN HTML formatında ver. Başlıklar için <h3> kullan, paragraflar için <p>, listeler için <ul>/<li> kullan. 
ASLA "###" gibi markdown başlıklarını kullanma. Yanıt doğrudan <h3> etiketiyle başlamalıdır. Somut rakamlarla destekle."""

    if analysis_type == 'daily':
        prompt = f"""Sen bir kişisel finans danışmanısın. Aşağıdaki GÜNLÜK harcama verilerini detaylı analiz et ve Türkçe olarak yanıt ver.
Bu analiz bugünün (tek günlük) harcamalarına odaklanmalıdır.

{base_stats}

## Lütfen şu başlıklar altında GÜNLÜK analiz yap:

### <i class="bi bi-sun-fill"></i> Günün Harcama Özeti
Bugün toplam ne kadar harcandı? Hangi kategorilerde harcama yapıldı? Kategorileri simgeleriyle birlikte listele.

### <i class="bi bi-clock-history"></i> Saat Bazlı Dağılım
Günün hangi saatlerinde harcama yoğunlaştı? Sabah/öğle/akşam dağılımı nasıl?

### <i class="bi bi-search"></i> Dürtüsel Alışveriş Kontrolü
Bugün dürtüsel alışveriş yapılmış mı? Plansız harcamalar var mı?

### <i class="bi bi-graph-up-arrow"></i> Günlük Bütçe Değerlendirmesi
Bugünkü harcama makul bir günlük bütçe içinde mi? Ortalama günlük harcamaya kıyasla nasıl?

### <i class="bi bi-basket2-fill"></i> Kategori Detayları
Her kategorideki harcamaları detaylı incele. Hangi harcamalar zorunlu, hangileri isteğe bağlı?

### <i class="bi bi-lightbulb"></i> Günün Tasarruf Fırsatları
Bugün hangi harcamalardan tasarruf edilebilirdi? Somut önerilerle açıkla.

### <i class="fa-regular fa-light-emergency-on"></i> Günlük Uyarılar
Dikkat edilmesi gereken noktalar neler? Günlük harcama limiti aşıldı mı?

{format_directives}"""

    elif analysis_type == 'weekly':
        prompt = f"""Sen bir kişisel finans danışmanısın. Aşağıdaki HAFTALIK harcama verilerini detaylı analiz et ve Türkçe olarak yanıt ver.
Bu analiz bu haftanın harcamalarına odaklanmalıdır.

{base_stats}

## Lütfen şu başlıklar altında HAFTALIK analiz yap:

### <i class="bi bi-calendar-week"></i> Haftalık Harcama Özeti
Bu hafta toplam ne kadar harcandı? Kategori bazlı dağılımı özetle. Kategorileri simgeleriyle birlikte listele.

### <i class="bi bi-bar-chart-steps"></i> Gün Gün Dağılım
Haftanın hangi günlerinde daha çok harcama yapıldı? En yoğun ve en sakin günler hangileri?

### <i class="bi bi-arrow-left-right"></i> Hafta İçi vs Hafta Sonu
Hafta içi ve hafta sonu harcamaları arasındaki fark nedir? Hangi dönemde daha fazla harcanıyor?

### <i class="bi bi-search"></i> Haftalık Dürtüsel Alışveriş Analizi
Bu hafta dürtüsel alışveriş kalıpları var mı? Hangi günlerde ve saatlerde yoğunlaşıyor?

### <i class="bi bi-exclamation-triangle"></i> Haftalık Anomaliler
Bu hafta alışılmışın dışında harcamalar var mı? Ortalamadan sapan harcamalar neler?

### <i class="bi bi-arrow-repeat"></i> Tekrarlayan Harcamalar
Bu hafta tekrar eden harcama kalıpları var mı? Gereksiz tekrarlar tespit edildi mi?

### <i class="bi bi-piggy-bank"></i> Haftalık Tasarruf Potansiyeli
Bu hafta ne kadar tasarruf edilebilirdi? Somut öneriler sun.

### <i class="bi bi-graph-up-arrow"></i> Haftalık Trend
Haftanın başından sonuna harcama trendi nasıl? Artış/azalış var mı?

### <i class="fa-regular fa-crystal-ball"></i> Aylık Projeksiyon
Bu haftanın harcama hızıyla devam edilirse ay sonunda toplam ne kadar harcanır?

### <i class="fa-regular fa-light-emergency-on"></i> Haftalık Uyarılar
Bu hafta dikkat edilmesi gereken noktalar neler?

{format_directives}"""

    else:
        # general / monthly
        prompt = f"""Sen bir kişisel finans danışmanısın. Aşağıdaki harcama verilerini detaylı analiz et ve Türkçe olarak yanıt ver.

{base_stats}

## Lütfen şu başlıklar altında analiz yap:

### <i class="bi bi-bar-chart-fill"></i> Genel Harcama Özeti
Toplam harcamaları ve kategori bazlı dağılımı özetle. Kategorileri belirtirken mutlaka simgelerini kullan: {cat_icons}

### <i class="bi bi-search"></i> Dürtüsel Alışveriş Tespiti
Dürtüsel (impulsive) alışveriş kalıpları var mı? Hangi kategorilerde ve saatlerde yoğunlaşıyor?

### <i class="bi bi-exclamation-triangle"></i> Anomali Tespiti
Alışılmışın dışında harcamalar var mı? Ortalamadan sapan harcamalar neler?

### <i class="bi bi-bar-chart-steps"></i> Davranış Deseni Analizi
Harcama alışkanlıkları hakkında ne söylenebilir? En çok hangi gün/saat harcama yapılıyor?

### <i class="bi bi-arrow-repeat"></i> Gereksiz Tekrarlar
Tekrarlayan, potansiyel olarak gereksiz harcamalar var mı?

### <i class="bi bi-lightbulb"></i> Alternatif Öneriler
Tasarruf için somut öneriler sun. Hangi harcamalar kısılabilir?

### <i class="fa-regular fa-crystal-ball"></i> Sonraki Ay Tahmini
Mevcut trende göre sonraki ay tahmini harcama ne olabilir?

### <i class="fa-regular fa-light-emergency-on"></i> Uyarılar
Dikkat edilmesi gereken noktalar neler?

{format_directives}"""

    import time

    genai.configure(api_key=api_key)

    # Sırasıyla denenecek modeller
    models_to_try = ['gemini-3-flash-preview']
    last_error = None

    for model_name in models_to_try:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            analysis_text = response.text

            return jsonify({
                'analysis': analysis_text,
                'analysis_type': analysis_type,
                'stats': {
                    'total': total,
                    'count': len(filtered),
                    'avg_daily': avg_daily,
                    'category_totals': cat_totals
                }
            })
        except Exception as e:
            last_error = str(e)
            if '429' in last_error:
                # Kota aşıldı - kısa bir süre bekleyip sonraki modeli dene
                time.sleep(5)
                continue
            else:
                return jsonify({'error': f'AI analizi sırasında hata: {last_error}'}), 500

    # Tüm modeller başarısız oldu
    error_msg = (
        'API kota limitiniz dolmuş görünüyor. Lütfen şunları deneyin:\n'
        '1. Birkaç dakika bekleyip tekrar deneyin\n'
        '2. Google AI Studio\'dan yeni bir API anahtarı oluşturun\n'
        '3. API planınızı kontrol edin: https://ai.google.dev/gemini-api/docs/rate-limits'
    )
    return jsonify({'error': error_msg}), 429


if __name__ == '__main__':
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    if not os.path.exists(DATA_FILE):
        save_expenses([])
    app.run(debug=True, port=5000)
