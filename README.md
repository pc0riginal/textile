# Textile Business Management System

A comprehensive full-stack web application for managing textile/fabric trading businesses built with FastAPI, MongoDB, and modern web technologies.

## Features

### Core Functionality
- **Multi-Company Management**: Manage multiple business entities with independent data
- **Party Management**: Handle customers, suppliers, brokers, and transporters
- **Purchase Management**: Grey challan entry with inventory tracking
- **Sales Management**: Invoice generation with stock selection
- **Advanced Inventory Transfers**: Material distribution with complete lineage tracking
- **Payment Management**: Receipt/payment entry with invoice settlement
- **Bank Integration**: Bank account management and reconciliation
- **Comprehensive Reports**: Financial, business, and compliance reports
- **GST Compliance**: Automatic tax calculations and GST-ready reports

### Key Highlights
- **Material Lineage Tracking**: Complete traceability of material movement from source to destination
- **Real-time Inventory Management**: Box-level tracking with transfer validation
- **Multi-recipient Transfers**: Transfer material from one source to multiple recipients
- **Automated Challan Creation**: Auto-generate recipient challans during transfers
- **Advanced Search**: Party search with autocomplete functionality
- **Responsive Design**: Modern UI with Tailwind CSS and Alpine.js

## Technology Stack

- **Backend**: FastAPI (Python)
- **Database**: MongoDB with Motor (async driver)
- **Frontend**: Server-side rendering with Jinja2 templates
- **Styling**: Tailwind CSS
- **Interactivity**: Alpine.js
- **Authentication**: JWT with HTTP-only cookies
- **Containerization**: Docker & Docker Compose

## Quick Start

### Using Docker (Recommended)

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd textile
   ```

2. **Start with Docker Compose**
   ```bash
   docker-compose up -d
   ```

3. **Access the application**
   - Open http://localhost:8000 in your browser
   - Use demo credentials: `admin` / `admin123`

### Manual Setup

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up MongoDB**
   - Install MongoDB locally or use MongoDB Atlas
   - Update `MONGODB_URL` in `.env` file

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

4. **Run the application**
   ```bash
   uvicorn main:app --reload
   ```

## Project Structure

```
textile_erp/
├── main.py                     # FastAPI app entry point
├── config.py                   # Configuration settings
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Docker configuration
├── docker-compose.yml         # Docker Compose setup
│
├── app/
│   ├── database.py            # MongoDB connection
│   ├── auth.py                # Authentication logic
│   ├── dependencies.py        # FastAPI dependencies
│   │
│   ├── models/                # Pydantic models
│   │   ├── user.py
│   │   ├── company.py
│   │   ├── party.py
│   │   ├── challan.py
│   │   └── transfer.py
│   │
│   ├── routers/               # API routes
│   │   ├── auth.py
│   │   ├── dashboard.py
│   │   ├── companies.py
│   │   ├── parties.py
│   │   ├── challans.py
│   │   └── transfers.py
│   │
│   ├── services/              # Business logic
│   │   └── inventory_service.py
│   │
│   ├── templates/             # Jinja2 templates
│   │   ├── base.html
│   │   ├── dashboard.html
│   │   ├── companies/
│   │   ├── parties/
│   │   ├── challans/
│   │   └── transfers/
│   │
│   └── static/                # Static files
│       ├── css/
│       ├── js/
│       └── images/
```

## Key Features Explained

### Inventory Transfer System

The system implements a sophisticated inventory transfer mechanism:

1. **Source Selection**: Choose from available purchase challans with inventory
2. **Multi-recipient Support**: Transfer to multiple parties in a single operation
3. **Automatic Validation**: Real-time checks for available quantity
4. **Challan Auto-creation**: Automatically creates new challans for recipients
5. **Lineage Tracking**: Complete material movement history
6. **Reversal Support**: Ability to reverse transfers with inventory restoration

### Material Lineage

Track complete material journey:
- Original purchase challan
- All transfer operations
- Current location and ownership
- Visual flow representation
- Audit trail with timestamps

### Multi-Company Architecture

- Independent data partitioning by company
- Company switching in navigation
- Role-based access control
- Separate financial years and document series

## Database Collections

### Key Collections
- `users`: User accounts and authentication
- `companies`: Business entities
- `parties`: Customers, suppliers, brokers, transporters
- `purchase_challans`: Purchase records with inventory tracking
- `inventory_transfers`: Transfer operations and lineage
- `sales_invoices`: Sales transactions
- `payments`: Payment records and settlements
- `bank_accounts` & `bank_transactions`: Banking operations

### Inventory Tracking Fields
Each purchase challan maintains:
- `total_boxes/meters`: Original quantity
- `available_boxes/meters`: Current available quantity
- `transferred_boxes/meters`: Total transferred out
- `is_transfer_source`: Has material been transferred from this challan
- `is_received_via_transfer`: Was this challan created via transfer
- `transfer_source_id`: Link to original source (if applicable)

## API Endpoints

### Authentication
- `POST /auth/login` - User login
- `POST /auth/register` - User registration
- `GET /auth/logout` - User logout

### Core Operations
- `GET /dashboard` - Dashboard with metrics
- `GET|POST /companies` - Company management
- `GET|POST /parties` - Party management
- `GET|POST /challans` - Purchase challan operations
- `GET|POST /transfers` - Inventory transfer operations

### Advanced Features
- `GET /transfers/tracking` - Transfer tracking and chains
- `GET /transfers/lineage/{challan_id}` - Material lineage view
- `GET /parties/search` - Party search API
- `POST /transfers/reverse/{transfer_id}` - Reverse transfer operation

## Development

### Adding New Features

1. **Create Model**: Add Pydantic model in `app/models/`
2. **Create Router**: Add FastAPI router in `app/routers/`
3. **Create Templates**: Add Jinja2 templates in `app/templates/`
4. **Update Navigation**: Modify sidebar in `app/templates/components/sidebar.html`
5. **Register Router**: Include router in `main.py`

### Database Operations

The application uses MongoDB with Motor for async operations:

```python
from app.database import get_collection

# Get collection
collection = await get_collection("collection_name")

# Insert document
result = await collection.insert_one(document)

# Find documents
documents = await collection.find(filter).to_list(None)

# Update document
await collection.update_one(filter, update)
```

### Inventory Service

The `InventoryService` class handles complex transfer operations:

```python
from app.services.inventory_service import InventoryService

service = InventoryService()
transfer_id = await service.create_transfer(company_id, transfer_data, user_id)
```

## Production Deployment

### Environment Variables
```bash
MONGODB_URL=mongodb://username:password@host:port/database
DATABASE_NAME=textile_erp
SECRET_KEY=your-super-secret-key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

### Security Considerations
- Change default secret key
- Use strong MongoDB credentials
- Enable HTTPS in production
- Implement rate limiting
- Regular security updates

### Performance Optimization
- Database indexing on frequently queried fields
- Connection pooling for MongoDB
- Static file serving via CDN
- Caching for frequently accessed data

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support and questions:
- Create an issue in the repository
- Check the documentation
- Review the code examples

---

**Note**: This is a comprehensive business management system. Ensure proper testing before using in production environments.