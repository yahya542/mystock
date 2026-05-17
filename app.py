from flask import Flask, request
from flask_cors import CORS
from flask_restx import Api, Resource, fields
import requests
import os
from dotenv import load_dotenv
import sqlite3
from datetime import datetime

# Load environment variables from .env file
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default_secret_key')

# Enable CORS for React Native access
CORS(app)

# Initialize Flask-RESTx API with Swagger documentation
api = Api(
    app,
    version='1.0',
    title='Stok Pulsa API',
    description='API Documentation for Stok Pulsa Backend\n\n'
                '**Features:**\n'
                '- Product Management (CRUD)\n'
                '- Phone Number Verification\n'
                '- Bulk Import Support\n\n'
                '**Base URL:** `/api`',
    doc='/',
    prefix='/api'
)

# Define Namespaces (like DRF routers)
products_ns = api.namespace('products', description='Product Operations')
phone_ns = api.namespace('phone', description='Phone Number Operations')

# Configuration
API_KEY_PROVIDER = os.getenv('API_KEY_PROVIDER')
FLASK_ENV = os.getenv('FLASK_ENV', 'development')
DATABASE = 'stok_kartu.db'


def get_db_connection():
    """Create database connection"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database with required tables"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create products table with simplified structure
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT UNIQUE NOT NULL,
            operator TEXT NOT NULL CHECK(operator IN ('telkomsel', 'xl', 'byu', 'axis', 'indosat', 'tri', 'smartfren')),
            location TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create index for faster search
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_phone_number 
        ON products(phone_number)
    ''')
    
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_operator 
        ON products(operator)
    ''')
    
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_location 
        ON products(location)
    ''')
    
    conn.commit()
    conn.close()


# Initialize database on startup
init_db()


# Define API Models (like DRF Serializers)
product_model = api.model('Product', {
    'id': fields.Integer(readonly=True, description='Product ID'),
    'phone_number': fields.String(required=True, description='Phone Number'),
    'operator': fields.String(required=True, enum=['telkomsel', 'xl', 'byu', 'axis', 'indosat', 'tri', 'smartfren'], description='Operator'),
    'location': fields.String(required=True, description='Location'),
    'status': fields.String(description='Status (active/inactive)'),
    'created_at': fields.String(description='Created Timestamp')
})

product_check_model = api.model('ProductCheck', {
    'phone_number': fields.String(required=True, description='Phone Number to Check')
})

product_add_model = api.model('ProductAdd', {
    'phone_number': fields.String(required=True, description='Phone Number'),
    'operator': fields.String(required=True, enum=['telkomsel', 'xl', 'byu', 'axis', 'indosat', 'tri', 'smartfren'], description='Operator'),
    'location': fields.String(required=True, description='Location')
})

bulk_add_model = api.model('BulkAdd', {
    'phone_numbers': fields.List(fields.String, required=True, description='List of Phone Numbers'),
    'operator': fields.String(required=True, enum=['telkomsel', 'xl', 'byu', 'axis', 'indosat', 'tri', 'smartfren'], description='Operator'),
    'location': fields.String(required=True, description='Location')
})

product_update_model = api.model('ProductUpdate', {
    'phone_number': fields.String(description='Phone Number'),
    'operator': fields.String(enum=['telkomsel', 'xl', 'byu', 'axis', 'indosat', 'tri', 'smartfren'], description='Operator'),
    'location': fields.String(description='Location'),
    'status': fields.String(description='Status')
})

# Operator choices constant
OPERATOR_CHOICES = ['telkomsel', 'xl', 'byu', 'axis', 'indosat', 'tri', 'smartfren']


# Health check endpoint (keep as simple Flask route)
@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    from flask import jsonify
    return jsonify({
        'status': 'success',
        'message': 'API is running',
        'environment': FLASK_ENV,
        'docs': '/api/docs'
    }), 200


# Product Check Endpoint
@phone_ns.route('/add')
class PhoneAdd(Resource):
    """Add single phone number to database"""
    
    @phone_ns.expect(product_add_model)
    @phone_ns.response(201, 'Phone number added successfully')
    @phone_ns.response(400, 'Invalid input')
    @phone_ns.response(409, 'Phone number already exists')
    def post(self):
        """Add a new phone number manually to database"""
        data = request.get_json()
        
        if not data or 'phone_number' not in data:
            return {'status': 'error', 'message': 'phone_number is required'}, 400
        
        phone_number = data['phone_number'].strip()
        operator = data.get('operator', '').strip().lower()
        location = data.get('location', '').strip()
        status = data.get('status', 'active')
        
        if not phone_number:
            return {'status': 'error', 'message': 'phone_number cannot be empty'}, 400
        
        if not operator or operator not in OPERATOR_CHOICES:
            return {'status': 'error', 'message': f'Invalid operator. Choose from: {", ".join(OPERATOR_CHOICES)}'}, 400
        
        if not location:
            return {'status': 'error', 'message': 'location is required'}, 400
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('SELECT id FROM products WHERE phone_number = ?', (phone_number,))
            existing = cursor.fetchone()
            
            if existing:
                conn.close()
                return {
                    'status': 'error',
                    'message': 'Nomor sudah ada dalam database',
                    'data': {'phone_number': phone_number, 'exists': True}
                }, 409
            
            cursor.execute('''
                INSERT INTO products (phone_number, operator, location, status)
                VALUES (?, ?, ?, ?)
            ''', (phone_number, operator, location, status))
            
            conn.commit()
            product_id = cursor.lastrowid
            conn.close()
            
            return {
                'status': 'success',
                'data': {
                    'id': product_id,
                    'phone_number': phone_number,
                    'operator': operator,
                    'location': location,
                    'status': status,
                    'exists': True
                },
                'message': 'Nomor berhasil ditambahkan ke database'
            }, 201
            
        except Exception as e:
            return {'status': 'error', 'message': f'Database error: {str(e)}'}, 500


@phone_ns.route('/add-bulk')
class PhoneBulkAdd(Resource):
    """Bulk add phone numbers to database"""
    
    @phone_ns.expect(bulk_add_model)
    @phone_ns.response(201, 'Phone numbers added successfully')
    @phone_ns.response(400, 'Invalid input')
    def post(self):
        """Add multiple phone numbers at once"""
        data = request.get_json()
        
        if not data or 'phone_numbers' not in data:
            return {'status': 'error', 'message': 'phone_numbers (array) is required'}, 400
        
        phone_numbers = data['phone_numbers']
        
        if not isinstance(phone_numbers, list) or len(phone_numbers) == 0:
            return {'status': 'error', 'message': 'phone_numbers must be a non-empty array'}, 400
        
        operator = data.get('operator', '').strip().lower()
        location = data.get('location', '').strip()
        
        if not operator or operator not in OPERATOR_CHOICES:
            return {'status': 'error', 'message': f'Invalid operator. Choose from: {", ".join(OPERATOR_CHOICES)}'}, 400
        
        if not location:
            return {'status': 'error', 'message': 'location is required'}, 400
        
        added = []
        duplicates = []
        errors = []
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            for phone_number in phone_numbers:
                phone_number = phone_number.strip()
                
                if not phone_number:
                    continue
                
                try:
                    cursor.execute('SELECT id FROM products WHERE phone_number = ?', (phone_number,))
                    existing = cursor.fetchone()
                    
                    if existing:
                        duplicates.append(phone_number)
                        continue
                    
                    cursor.execute('''
                        INSERT INTO products (phone_number, operator, location, status)
                        VALUES (?, ?, ?, 'active')
                    ''', (phone_number, operator, location))
                    
                    added.append(phone_number)
                    
                except Exception as e:
                    errors.append({'phone_number': phone_number, 'error': str(e)})
            
            conn.commit()
            conn.close()
            
            return {
                'status': 'success',
                'data': {
                    'added': added,
                    'duplicates': duplicates,
                    'errors': errors,
                    'total_added': len(added),
                    'total_duplicates': len(duplicates),
                    'total_errors': len(errors)
                },
                'message': f'Berhasil menambahkan {len(added)} nomor'
            }, 201
            
        except Exception as e:
            return {'status': 'error', 'message': f'Database error: {str(e)}'}, 500


@products_ns.route('/check')
class ProductCheck(Resource):
    """Check if phone number exists in database"""
    
    @products_ns.expect(product_check_model)
    @products_ns.response(200, 'Check completed')
    @products_ns.response(400, 'Invalid input')
    def post(self):
        """Check if phone number exists and get product info"""
        data = request.get_json()
        
        if not data or 'phone_number' not in data:
            return {'status': 'error', 'message': 'phone_number is required'}, 400
        
        phone_number = data['phone_number'].strip()
        
        if not phone_number:
            return {'status': 'error', 'message': 'phone_number cannot be empty'}, 400
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, phone_number, operator, location, status, created_at
                FROM products
                WHERE phone_number = ?
            ''', (phone_number,))
            
            product = cursor.fetchone()
            conn.close()
            
            if product:
                return {
                    'status': 'success',
                    'data': {
                        'exists': True,
                        'product': {
                            'id': product['id'],
                            'phone_number': product['phone_number'],
                            'operator': product['operator'],
                            'location': product['location'],
                            'status': product['status'],
                            'created_at': product['created_at']
                        }
                    },
                    'message': 'Nomor ditemukan dalam database'
                }, 200
            else:
                return {
                    'status': 'success',
                    'data': {
                        'exists': False,
                        'product': None
                    },
                    'message': 'Nomor tidak ditemukan dalam database'
                }, 200
                
        except Exception as e:
            return {'status': 'error', 'message': f'Database error: {str(e)}'}, 500


@products_ns.route('')
class ProductList(Resource):
    """Get all products or add new product"""
    
    @products_ns.marshal_list_with(product_model)
    @products_ns.response(200, 'Products retrieved successfully')
    def get(self):
        """Get all products with optional global search"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            status = request.args.get('status', None)
            operator = request.args.get('operator', None)
            search = request.args.get('search', None)
            
            query = 'SELECT id, phone_number, operator, location, status, created_at FROM products WHERE 1=1'
            params = []
            
            if status:
                query += ' AND status = ?'
                params.append(status)
            
            if operator:
                query += ' AND operator = ?'
                params.append(operator.lower())
            
            # Global search across all fields
            if search:
                query += ' AND (phone_number LIKE ? OR operator LIKE ? OR location LIKE ?)'
                search_param = f'%{search}%'
                params.extend([search_param, search_param, search_param])
            
            query += ' ORDER BY created_at DESC'
            
            cursor.execute(query, params)
            products = cursor.fetchall()
            conn.close()
            
            return products, 200
            
        except Exception as e:
            return {'status': 'error', 'message': f'Database error: {str(e)}'}, 500
    
    @products_ns.expect(product_add_model)
    @products_ns.response(201, 'Product created successfully')
    @products_ns.response(400, 'Invalid input')
    @products_ns.response(409, 'Phone number already exists')
    def post(self):
        """Add new product to database"""
        data = request.get_json()
        
        required_fields = ['phone_number', 'operator', 'location']
        if not data or not all(field in data for field in required_fields):
            return {'status': 'error', 'message': f'Required fields: {", ".join(required_fields)}'}, 400
        
        phone_number = data['phone_number'].strip()
        operator = data['operator'].strip().lower()
        location = data['location'].strip()
        status = data.get('status', 'active')
        
        if not phone_number or not operator or not location:
            return {'status': 'error', 'message': 'All fields are required'}, 400
        
        if operator not in OPERATOR_CHOICES:
            return {'status': 'error', 'message': f'Invalid operator. Choose from: {", ".join(OPERATOR_CHOICES)}'}, 400
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO products (phone_number, operator, location, status)
                VALUES (?, ?, ?, ?)
            ''', (phone_number, operator, location, status))
            
            conn.commit()
            product_id = cursor.lastrowid
            conn.close()
            
            return {
                'status': 'success',
                'data': {
                    'id': product_id,
                    'phone_number': phone_number,
                    'operator': operator,
                    'location': location,
                    'status': status
                },
                'message': 'Product berhasil ditambahkan'
            }, 201
            
        except sqlite3.IntegrityError:
            return {'status': 'error', 'message': 'Nomor sudah terdaftar dalam database'}, 409
        except Exception as e:
            return {'status': 'error', 'message': f'Database error: {str(e)}'}, 500


@products_ns.route('/<int:product_id>')
class ProductDetail(Resource):
    """Get, update or delete a specific product"""
    
    @products_ns.marshal_with(product_model)
    @products_ns.response(200, 'Product retrieved')
    @products_ns.response(404, 'Product not found')
    def get(self, product_id):
        """Get a specific product by ID"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, phone_number, operator, location, status, created_at
                FROM products WHERE id = ?
            ''', (product_id,))
            
            product = cursor.fetchone()
            conn.close()
            
            if not product:
                return {'status': 'error', 'message': 'Product tidak ditemukan'}, 404
            
            return product, 200
            
        except Exception as e:
            return {'status': 'error', 'message': f'Database error: {str(e)}'}, 500
    
    @products_ns.expect(product_update_model)
    @products_ns.response(200, 'Product updated successfully')
    @products_ns.response(404, 'Product not found')
    @products_ns.response(409, 'Phone number already exists')
    def put(self, product_id):
        """Update product information"""
        data = request.get_json()
        
        if not data:
            return {'status': 'error', 'message': 'No data provided'}, 400
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('SELECT id FROM products WHERE id = ?', (product_id,))
            if not cursor.fetchone():
                conn.close()
                return {'status': 'error', 'message': 'Product tidak ditemukan'}, 404
            
            allowed_fields = ['phone_number', 'operator', 'location', 'status']
            update_fields = []
            params = []
            
            for field in allowed_fields:
                if field in data:
                    update_fields.append(f'{field} = ?')
                    value = data[field]
                    # Auto-lowercase operator
                    if field == 'operator':
                        value = value.lower()
                        if value not in OPERATOR_CHOICES:
                            conn.close()
                            return {'status': 'error', 'message': f'Invalid operator. Choose from: {", ".join(OPERATOR_CHOICES)}'}, 400
                    params.append(value)
            
            if not update_fields:
                conn.close()
                return {'status': 'error', 'message': 'No valid fields to update'}, 400
            
            update_fields.append('updated_at = CURRENT_TIMESTAMP')
            params.append(product_id)
            
            query = f'UPDATE products SET {", ".join(update_fields)} WHERE id = ?'
            cursor.execute(query, params)
            
            conn.commit()
            conn.close()
            
            return {'status': 'success', 'message': 'Product berhasil diupdate'}, 200
            
        except sqlite3.IntegrityError:
            return {'status': 'error', 'message': 'Nomor sudah terdaftar dalam database'}, 409
        except Exception as e:
            return {'status': 'error', 'message': f'Database error: {str(e)}'}, 500
    
    @products_ns.response(200, 'Product deleted successfully')
    @products_ns.response(404, 'Product not found')
    def delete(self, product_id):
        """Delete a product from database"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('SELECT id FROM products WHERE id = ?', (product_id,))
            if not cursor.fetchone():
                conn.close()
                return {'status': 'error', 'message': 'Product tidak ditemukan'}, 404
            
            cursor.execute('DELETE FROM products WHERE id = ?', (product_id,))
            conn.commit()
            conn.close()
            
            return {'status': 'success', 'message': 'Product berhasil dihapus'}, 200
            
        except Exception as e:
            return {'status': 'error', 'message': f'Database error: {str(e)}'}, 500


if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=5008,
        debug=(FLASK_ENV == 'development')
    )
