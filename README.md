# FieldForce Dashboard - Coromandel

A comprehensive Flask-based web dashboard for analyzing agricultural fieldforce conversations and market intelligence for Coromandel and competitor tracking.

---

## 🚀 Quick Start

### Installation

1. **Clone or download the repository**

2. **Install dependencies:**
```bash
pip install flask Flask-Bcrypt
```

3. **Run the application:**
```bash
cd customer_dashboard-main
python app.py
```

4. **Access the dashboard:**
Open your browser and navigate to: **http://127.0.0.1:5000**

---

## 🔐 Login Credentials

The dashboard has two types of users with different access levels:

### **Full Admin Access**
- **Username:** `admin`
- **Password:** `adminpass`
- **Access Level:** Full access to all modules and technical metrics

### **Customer Admin Access**
- **Username:** `customer`
- **Password:** `customer123`
- **Access Level:** Limited access - business metrics only, no technical/system metrics

---

## 📊 Dashboard Modules

### 1. **HOME Module** 🏠
- **KPIs:** Alert Count, Activity Count, Market Health Score
- **Charts:**
  - Volume & Sentiment Trend (time-series)
  - Conversation Distribution (doughnut chart)
  - Market Share Over Time
  - Competitive Position Table
  - Top Conversation Drivers

### 2. **MARKETING Module** 📈
- Brand Health Trend
- Conversation Volume by Topic
- Brand Keywords Word Cloud
- Market Share Trend
- Competitive Landscape (bubble chart)
- Sentiment by Competitor
- Brand-Crop Association (sunburst diagram)

### 3. **OPERATIONS Module** 🛠️
- Urgent Issues Table
- Demand Signal Trend
- Demand Change Alerts
- Crop-Pest Heatmap
- Problem Trend Analysis
- Problem Sentiment Distribution
- Crop Keywords Word Cloud
- Solution Flow (Sankey diagram)
- Solution Effectiveness
- Solution Sentiment Trend
- Sentiment by Crop

### 4. **ENGAGEMENT Module** 👥
- Conversations by Region
- Team Urgency Distribution
- Team Intent Analysis
- Quality by Region
- Agent Scorecard Table
- Agent Leaderboard
- Agent Performance Trend
- Field Leaders (bubble chart)
- Sentiment by Entity
- Topic Distribution
- Training Needs Analysis

### 5. **ADMIN Module** ⚙️

**Full Admin View:**
- Total Records KPI
- Data Completeness KPI
- Active Users KPI
- Date Coverage KPI
- Dashboard Users Table
- User Activity Log Table
- Database Statistics
- Data Completeness Metrics

**Customer Admin View (Limited):**
- Active Users KPI
- Date Coverage KPI
- Dashboard Users Table
- User Activity Log Table
- ❌ No Database Statistics
- ❌ No Data Completeness Metrics

---

## 🔒 Role-Based Access Control

### Access Comparison Table

| Feature | Admin | Customer Admin |
|---------|-------|----------------|
| HOME Module | ✅ Full Access | ✅ Full Access |
| MARKETING Module | ✅ Full Access | ✅ Full Access |
| OPERATIONS Module | ✅ Full Access | ✅ Full Access |
| ENGAGEMENT Module | ✅ Full Access | ✅ Full Access |
| ADMIN - User Tables | ✅ Visible | ✅ Visible |
| ADMIN - Active Users KPI | ✅ Visible | ✅ Visible |
| ADMIN - Date Coverage KPI | ✅ Visible | ✅ Visible |
| ADMIN - Total Records KPI | ✅ Visible | ❌ Hidden |
| ADMIN - Data Completeness KPI | ✅ Visible | ❌ Hidden |
| ADMIN - Database Statistics | ✅ Visible | ❌ Hidden |
| ADMIN - Completeness Metrics | ✅ Visible | ❌ Hidden |

---

## 🗄️ Database Information

**Database Type:** SQLite  
**Database File:** `fieldforce.db`  
**Location:** `customer_dashboard-main/fieldforce.db`

### Database Schema

**Fact Tables (Transaction Data):**
- `fact_conversations` - Core conversation records
- `fact_conversation_entities` - Extracted entities (brands, crops, pests)
- `fact_conversation_semantics` - Sentiment, intent, urgency analysis
- `fact_conversation_metrics` - Alert flags and metrics

**Dimension Tables (Master Data):**
- `dim_brands` - Brand catalog
- `dim_companies` - Company information (Coromandel, competitors)
- `dim_crops` - Crop catalog with types
- `dim_pests` - Pest catalog
- `dim_user` - Field force user information
- `dim_dashboard_users` - Dashboard login users

**Mart Tables (Pre-aggregated Analytics):**
- `mart_brand_crop_matrix` - Brand-crop co-mentions
- `mart_crop_pest_matrix` - Crop-pest co-mentions
- `mart_crop_pest_brand_flow` - Complete solution flow analysis

---

## 🎯 Competitor Tracking

**Primary Company:** Coromandel (Code: 7007)

**Tracked Competitors:**
1. Bayer Crop Science (Code: 7002)
2. UPL Limited (Code: 7025)
3. Syngenta India Ltd (Code: 7024)

---

## 📝 Recent Changes & Updates

### **Version 2.0 - Role-Based Dashboard Split**

#### **1. Authentication System (`auth.py`)**
- ✅ Added role-based user system (admin vs customer_admin)
- ✅ Modified `add_user()` to accept role parameter
- ✅ Updated `check_password()` to return (success, role) tuple
- ✅ Added `get_user_role()` utility function
- ✅ Backward compatibility with old user format
- ✅ Automatic migration of existing users to new format

#### **2. Application Backend (`app.py`)**
- ✅ Updated `/login` route to capture and store user role in session
- ✅ Updated `/register` route to support role assignment
- ✅ Modified dashboard route to pass `user_role` to template
- ✅ Created default admin and customer users on initialization

#### **3. Dashboard Frontend (`templates/dashboard.html`)**
- ✅ Added role-based CSS classes for visibility control
- ✅ Body tag dynamically receives role class (admin or customer-admin)
- ✅ Added user info in header:
  - Username display
  - Role badge (ADMIN or CUSTOMER)
  - Logout button
- ✅ Marked admin-only sections in ADMIN module:
  - Total Records KPI (hidden from customers)
  - Data Completeness KPI (hidden from customers)
  - Database Statistics section (hidden from customers)
  - Data Completeness Metrics section (hidden from customers)

#### **4. Files Modified**
- `auth.py` - ~45 lines modified/added
- `app.py` - ~15 lines modified
- `templates/dashboard.html` - ~25 lines modified

#### **5. Backward Compatibility**
✅ Existing users are automatically migrated:
- Old format users detected and converted to new format
- Old users receive "admin" role by default
- Migration happens automatically on first login
- No breaking changes to existing functionality

---

## 🔧 Technical Stack

**Backend:**
- Flask (Web Framework)
- Flask-Bcrypt (Password Hashing)
- SQLite3 (Database)
- Python 3.x

**Frontend:**
- HTML5
- CSS3
- JavaScript (Vanilla)
- Chart.js (Data Visualization)
- WordCloud2.js (Word Clouds)

**Deployment:**
- Local Development Server (Flask)
- Azure Web App Ready (configured for Azure deployment)

---

## 🌐 API Endpoints

### Filter Options
- `GET /api/filters/crops` - Get crop options
- `GET /api/filters/crop-types` - Get crop type options

### Home Module
- `GET /api/home/kpis` - Get home KPIs
- `GET /api/home/volume-sentiment` - Volume & sentiment trend
- `GET /api/home/conversation-distribution` - Conversation distribution
- `GET /api/home/market-share` - Market share data
- `GET /api/home/competitive-position` - Competitive position
- `GET /api/home/conversation-drivers` - Conversation drivers

### Marketing Module
- `GET /api/marketing/brand-health-trend` - Brand health trend
- `GET /api/marketing/conv-volume-by-topic` - Conversation volume by topic
- `GET /api/marketing/brand-keywords` - Brand keywords
- `GET /api/marketing/market-share-trend` - Market share trend
- `GET /api/marketing/competitive-landscape` - Competitive landscape
- `GET /api/marketing/sentiment-by-competitor` - Sentiment by competitor
- `GET /api/marketing/brand-crop-association` - Brand-crop association

### Operations Module
- `GET /api/operations/urgent-issues` - Urgent issues list
- `GET /api/operations/demand-signal-trend` - Demand signal trend
- `GET /api/operations/demand-change-alert` - Demand change alerts
- `GET /api/operations/crop-pest-heatmap` - Crop-pest heatmap
- `GET /api/operations/problem-trend` - Problem trend
- `GET /api/operations/problem-sentiment` - Problem sentiment
- `GET /api/operations/crop-keywords` - Crop keywords
- `GET /api/operations/solution-flow` - Solution flow
- `GET /api/operations/solution-effectiveness` - Solution effectiveness
- `GET /api/operations/solution-sentiment` - Solution sentiment
- `GET /api/operations/sentiment-by-crop` - Sentiment by crop

### Engagement Module
- `GET /api/engagement/conv-by-region` - Conversations by region
- `GET /api/engagement/team-urgency` - Team urgency
- `GET /api/engagement/team-intent` - Team intent
- `GET /api/engagement/quality-by-region` - Quality by region
- `GET /api/engagement/agent-scorecard` - Agent scorecard
- `GET /api/engagement/agent-leaderboard` - Agent leaderboard
- `GET /api/engagement/agent-perf-trend` - Agent performance trend
- `GET /api/engagement/field-leaders` - Field leaders
- `GET /api/engagement/sentiment-by-entity` - Sentiment by entity
- `GET /api/engagement/topic-distribution` - Topic distribution
- `GET /api/engagement/training-needs` - Training needs

### Admin Module
- `GET /api/admin/users` - Dashboard users
- `GET /api/admin/user-activity-log` - User activity log
- `GET /api/admin/completeness-kpi` - Data completeness KPIs
- `GET /api/admin/db-stats` - Database statistics
- `GET /api/debug/companies` - Debug company data

---

## 📱 Features

### Data Filtering
- Date range filtering (7/30/60/90/365 days, all time, custom range)
- Crop type filtering
- Crop name filtering
- Company filtering
- Geography filtering

### Visualization Types
- Line charts (trends over time)
- Bar charts (comparisons)
- Doughnut/Pie charts (distributions)
- Bubble charts (multi-dimensional data)
- Heatmaps (correlation matrices)
- Word clouds (keyword analysis)
- Sankey diagrams (flow analysis)
- Data tables (detailed records)

### User Interface
- Responsive design
- Modern color scheme (green/orange/teal)
- Interactive charts with hover tooltips
- Smooth transitions and animations
- Module-based navigation
- Real-time data loading with spinners

---

## 🔄 Azure Deployment

The application is configured for Azure Web App deployment:

**Azure Commands:**
```bash
# View logs
az webapp log tail --name thankful-mushroom-2064f2ae731b4b9aa426c291a89af8e --resource-group philip.derbeko_rg_1429

# SSH into Azure instance
az webapp ssh --name thankful-mushroom-2064f2ae731b4b9aa426c291a89af8e1 --resource-group philip.derbeko_rg_1429
```

**Azure Configuration:**
- Database path automatically switches to `/home/site/data/fieldforce.db`
- Detects Azure environment via `WEBSITE_INSTANCE_ID` variable

---

## 🛠️ Development

### Project Structure
```
customer_dashboard-main/
├── app.py                  # Main Flask application
├── auth.py                 # Authentication module
├── fieldforce.db          # SQLite database
├── requirements.txt       # Python dependencies
├── users.json            # User credentials storage
├── templates/
│   ├── dashboard.html    # Main dashboard UI
│   ├── login.html        # Login page
│   ├── register.html     # Registration page
│   └── index.html        # Index/landing page
└── README.md             # This file
```

### Running in Debug Mode
The application runs in debug mode by default:
- Auto-reload on code changes
- Detailed error messages
- Debug toolbar available

### Adding New Users
Users can be added programmatically in `app.py`:
```python
auth.add_user("username", "password", role="admin")  # or "customer_admin"
```

Or through the registration page (defaults to customer_admin role).

---

## 📊 Use Cases

1. **Marketing Teams:** Track brand health, competitive positioning, sentiment analysis
2. **Operations Teams:** Monitor urgent issues, crop-pest problems, demand signals
3. **Field Force Management:** Agent performance tracking, training needs identification
4. **Regional Managers:** Geographic insights, quality metrics by region
5. **Business Intelligence:** Market share trends, conversation drivers, topic analysis

---

## 🔐 Security Features

- ✅ Bcrypt password hashing
- ✅ Session-based authentication
- ✅ Login required decorator on all API endpoints
- ✅ Role-based access control
- ✅ Automatic logout functionality
- ✅ Password validation on login

---

## 📄 License

See LICENSE file for details.

---

## 👥 Support

For issues or questions, please contact your system administrator or refer to the deployment documentation.

---

## 🎯 Version History

**Version 2.0** (Current)
- Added role-based access control
- Split dashboard into Admin and Customer Admin views
- Enhanced security with role management
- Added user info display in header
- Backward compatibility with existing users

**Version 1.0**
- Initial release
- Full dashboard with 5 modules
- SQLite database integration
- Azure deployment ready

---

**Last Updated:** December 2025
