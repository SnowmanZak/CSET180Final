from flask import Flask, render_template, request, redirect, url_for, jsonify
from sqlalchemy import create_engine, text
import bcrypt
import math
import traceback
import colorsys

app = Flask(__name__)

conn_str = "mysql://root:cset155@localhost/store"
engine = create_engine(conn_str, echo = True)
conn = engine.connect()

@app.context_processor
def inject_user():
    return {'user': get_logged_in_user()}



@app.route('/')
def home():
    user = get_logged_in_user()
    logged_in = bool(user)
    vendors =[]
    if user and user['user_type'] == 'customer':
        with engine.begin() as conn:
            result = conn.execute(text("SELECT user_id, name, username FROM users WHERE user_type = 'vendor'"))
            vendors = [dict(row._mapping) for row in result]
    
    # if user and user['user_type'] == 'vendor':
    #     with engine.begin() as conn:
    #         result = conn.execute(text("""
    #             SELECT u.user_id, u.name, u.username, MAX(c.sent_at) as last_sent
    #             FROM chat c
    #             JOIN users u ON c.sender_id = u.user_id
    #             WHERE c.receiver_id = :user_id
    #             GROUP BY u.user_id, u.name, u.username
    #             ORDER BY last_sent DESC
    #         """), {'user_id': user['user_id']})
    
    #     incoming_chats = [dict(row) for row in result]
    # else:
    #     incoming_chats = []

    return render_template('index.html', logged_in=logged_in, user=user, vendors=vendors)



@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        username = request.form.get('username')
        password = request.form.get('password')
        user_type = request.form.get('role')  

        hashed_password = hash_password(password)

        try:
            with engine.begin() as conn:
                check_existing = conn.execute(
                    text('SELECT * FROM users WHERE username = :username'),
                    {'username': username}
                ).fetchone()

                if check_existing:
                    return render_template('signup.html', error="Username is already in use.")
                else:
                    log_other_users_out(conn)

                    conn.execute(
                        text('''
                            INSERT INTO users (name, email, username, password, user_type, logged_in)
                            VALUES (:name, :email, :username, :password, :user_type, :logged_in)
                        '''),
                        {
                            'name': name,
                            'email': email,
                            'username': username,
                            'password': hashed_password,
                            'user_type': user_type.lower(),  
                            'logged_in': True
                        }
                    )

                    return redirect(url_for('home'))

        except Exception as e:
            return render_template('signup.html', error=f'An error occurred: {str(e)}')

    return render_template('signup.html')



@app.route('/login', methods=['GET'])
def gologin():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    with engine.begin() as conn:
        username = request.form.get('username')
        password = request.form.get('password')

        user = conn.execute(
            text('SELECT * FROM users WHERE username = :username'),
            {'username': username}
        ).mappings().first()

        if user and check_password(password, user['password']):
            log_other_users_out(conn)

            conn.execute(
                text('UPDATE users SET logged_in = 1 WHERE user_id = :user_id'),
                {'user_id': user['user_id']}
            )

            logged_in_user = get_logged_in_user()       
            return redirect(url_for('home', user=logged_in_user, logged_in=True))
            
        else:
            return render_template('login.html', error="Invalid credentials.", logged_in=False)


@app.route('/log-out', methods=['GET', 'POST'])
def log_out():
    user = get_logged_in_user()
    
    with engine.begin() as conn:
        conn.execute(
            text('UPDATE users SET logged_in = 0 WHERE user_id = :uid'),
            {'uid': user['user_id']}
        )
    
    return render_template('index.html', logged_in = False)



@app.route('/account', methods=['GET'])
def account():
    user = get_logged_in_user()

    if not user:
        return redirect(url_for('login'))

    with engine.begin() as conn:
        result = conn.execute(
            text('SELECT user_id, name, email, username FROM users WHERE logged_in = 1 AND user_id = :user_id'),
            {'user_id': user['user_id']}
        )
        account_details = result.mappings().first()

    return render_template('account.html', user=user, account_details=account_details)




@app.route('/product-create', methods=['GET', 'POST'])
def product_create():
    user = get_logged_in_user()
    if not user:
        return redirect('/login')

    vendors = []

    if user['user_type'] == 'admin':
        with engine.connect() as conn:
            vendor_rows = conn.execute(text("SELECT user_id, username FROM users WHERE user_type = 'vendor'")).mappings().all()
            vendors = list(vendor_rows)

    if request.method == "POST":
        name = request.form.get('product-name')
        description = request.form.get('product-description')
        warranty_period = request.form.get('warranty-period')
        category = request.form.get('category')

        if user['user_type'] == 'admin':
            vendor_id = request.form.get('vendor_id')
            if not vendor_id:
                return render_template('productCreate.html', user_type=user['user_type'], vendors=vendors, error="Vendor must be selected.")
        else:
            vendor_id = user['user_id']

        try:
            with engine.begin() as conn:
                conn.execute(text('''
                    INSERT INTO products (title, description, warranty_period, category, vendor_id)
                    VALUES (:title, :description, :warranty, :category, :vendor_id)
                '''), {
                    'title': name,
                    'description': description,
                    'warranty': warranty_period,
                    'category': category.lower(),
                    'vendor_id': vendor_id
                })

            return render_template('productCreate.html', step_one_creation_submit=True, user_type=user['user_type'], vendors=vendors)

        except Exception as e:
            print("Error creating product:", e)
            return render_template('productCreate.html', step_one_creation_submit=False, user_type=user['user_type'], vendors=vendors)

    return render_template('productCreate.html', user_type=user['user_type'], vendors=vendors)




color_list = [] # Global variable for add-color

@app.route('/add-color', methods=['GET', 'POST'])
def add_color():

    if request.method == "POST":
        color = request.form.get('product-color')
        
        global color_list
        rows = math.ceil(len(color_list) / 12)
        
        if color in color_list:
            return render_template('productCreate.html', step_one_creation_submit=True, color_list=color_list, rows=range(rows))
        else:
            color_list.append(color)
            return render_template('productCreate.html', step_one_creation_submit=True, color_list=color_list, rows=range(rows))        
  


@app.route('/remove-color', methods=['GET', 'POST'])
def remove_color():
    color = request.args.get('color')
    global color_list
    
    if color in color_list:
        color_list.remove(color)
                
    return render_template("productCreate.html", color_list=color_list, step_one_creation_submit=True)



@app.route('/submit-color', methods=['GET', 'POST'])
def submit_color():
    product_id = get_product_id()  

    if not product_id:
        return "Error: Product ID not found."

    global color_list
    if not color_list:
        return render_template('productCreate.html', color_list=color_list, step_one_creation_submit=True, empty_list=True)

    try:
        with engine.begin() as conn:
            for color in color_list:
                
                color_group = get_color_category(color)
                
                conn.execute(
                    text('INSERT INTO availablecolors (product_id, color, color_group) VALUES (:product_id, :color, :color_group)'),
                    {'product_id': product_id, 'color': color, 'color_group': color_group}
                )

        color_list = []  
        

        return render_template('productCreate.html', step_two_creation_submit=True, step_one_creation_submit=False)

    except Exception as e:
        print(f'Color insert failed: {e}')
        return render_template('productCreate.html', step_two_creation_submit=False, step_one_creation_submit=True)



@app.route('/size-submit', methods=['POST'])
def size_submit():
    product_id = get_product_id()  

    if not product_id:
        return "Error: Product ID not found."

    selected_sizes = [size for size in ['xsmall', 'small', 'medium', 'large', 'xlarge'] if request.form.get(size)]
    print(f"Selected Sizes: {selected_sizes}")  

    try:
        with engine.begin() as conn:
            for size in selected_sizes:
                conn.execute(
                    text('INSERT INTO availablesizes (product_id, size) VALUES (:product_id, :size)'),
                    {'product_id': product_id, 'size': size}
                )


        return render_template('productCreate.html', step_three_creation_submit=True, step_two_creation_submit=False)

    except Exception as e:
        print(f"Error inserting sizes: {e}")
        return render_template('productCreate.html', step_three_creation_submit=True, step_two_creation_submit=False)



img_counter = 0

@app.route('/submit-image', methods=['POST'])
def submit_image():
    global img_counter

    image_url = request.form.get(f'image-{img_counter}')
    
    if image_url:
        product_id = get_product_id()

        if product_id is not None:
            with engine.connect() as conn:
                conn.execute(
                    text('INSERT INTO productimages (product_id, image_url) VALUES (:product_id, :image_url)'),
                    {'product_id': product_id, 'image_url': image_url}
                )
                conn.commit()

            img_counter += 1

    return redirect('/image-management')



@app.route('/image-management')
def image_management():
    global img_counter

    product_id = get_product_id()
    submitted_images = []

    if product_id:
        with engine.connect() as conn:
            result = conn.execute(
                text('SELECT image_id, image_url FROM productimages WHERE product_id = :product_id'),
                {'product_id': product_id}
            )
            submitted_images = [{'id': row[0], 'url': row[1]} for row in result.fetchall()]

    img_rows = math.ceil(len(submitted_images) / 4)

    return render_template('productCreate.html',
                           step_three_creation_submit=True,
                           img_rows=range(img_rows),
                           img_counter=img_counter,
                           submitted_images=submitted_images)



@app.route('/delete-image/<int:image_id>', methods=['POST'])
def delete_image(image_id):
    with engine.connect() as conn:
        conn.execute(
            text('DELETE FROM productimages WHERE image_id = :image_id'),
            {'image_id': image_id}
        )
        conn.commit()
    return redirect('/image-management')



@app.route('/finalize-images', methods=['POST'])
def finalize_images():
    global img_counter
    img_counter = 0 


    product_id = get_product_id()  
    print(f"Finalizing images for product ID {product_id}...")


    try:
        with engine.begin() as conn:
            result = conn.execute(text("""
                SELECT c.color_id, s.size_id
                FROM availablecolors c
                JOIN availablesizes s ON c.product_id = s.product_id
                WHERE c.product_id = :pid
            """), {'pid': product_id})

            rows = result.fetchall()
            print(f"Rows fetched: {rows}")  

            if not rows:
                print(f"No color-size combinations found for product ID {product_id}.")
            else:
                print(f"Found {len(rows)} combinations. Processing insert...")

                inserted_count = 0

                for row in rows:
                    color_id, size_id = row
                    print(f"Checking: color_id={color_id}, size_id={size_id}")

                    exists = conn.execute(text("""
                        SELECT 1 FROM productvariants
                        WHERE product_id = :pid AND color_id = :cid AND size_id = :sid
                    """), {'pid': product_id, 'cid': color_id, 'sid': size_id}).fetchone()

                    if exists:
                        print(f"Variant already exists for {color_id}, {size_id}")
                    else:
                        conn.execute(text("""
                            INSERT INTO productvariants (
                                product_id, color_id, size_id, inventory_count, price, discount_price, discount_end_date
                            ) VALUES (
                                :pid, :cid, :sid, 0, 0.00, NULL, NULL
                            )
                        """), {'pid': product_id, 'cid': color_id, 'sid': size_id})
                        print(f"Inserted variant for {color_id}, {size_id}")
                        inserted_count += 1

                print(f"{inserted_count} new variants inserted for product {product_id}.")

    except Exception as e:
        print("Error during variant insertion:")
        print(traceback.format_exc())

    return render_template('productCreate.html', step_four_creation_submit=True)



@app.route('/chat', methods=['GET', 'POST'])
def chat():
    user = get_logged_in_user()
    if not user:
        return redirect(url_for('home'))

    if request.method == 'GET':
        other_id = request.args.get('vendor_id') if user['user_type'] == 'customer' else request.args.get('customer_id')
        if not other_id:
            return redirect(url_for('home'))

        with engine.begin() as conn:
            messages = conn.execute(text("""
                SELECT * FROM chat
                WHERE (sender_id = :user_id AND receiver_id = :other_id)
                   OR (sender_id = :other_id AND receiver_id = :user_id)
                ORDER BY sent_at ASC
            """), {'user_id': user['user_id'], 'other_id': other_id}).fetchall()

        return render_template('chat.html', messages=messages, user=user, other_id=other_id)

    elif request.method == 'POST':
        message = request.form.get('message')
        receiver_id = request.form.get('receiver_id')

        if message and receiver_id:
            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO chat (sender_id, receiver_id, message)
                    VALUES (:sender_id, :receiver_id, :message)
                """), {'sender_id': user['user_id'], 'receiver_id': receiver_id, 'message': message})

        return redirect(url_for('chat', **(
            {'vendor_id': receiver_id} if user['user_type'] == 'customer' else {'customer_id': receiver_id}
        )))



@app.route('/view-products/')
@app.route('/view-products/<search>')
def view_products(search=None):
    
    print(f'This is the results: {search}')
    
    with engine.connect() as conn:
        if search == 'blank':
            return render_template('products.html', products='none')
        elif search:
            products = conn.execute(text("""
                SELECT p.product_id, p.title, p.description, p.warranty_period, u.name AS vendor_name
                FROM products p
                JOIN users u ON p.vendor_id = u.user_id
                WHERE LOWER(p.title) = :search
            """), {'search': search.lower()}).fetchall()
        else:
            products = conn.execute(text("""
                SELECT p.product_id, p.title, p.description, p.warranty_period, u.name AS vendor_name
                FROM products p
                JOIN users u ON p.vendor_id = u.user_id
            """)).fetchall()
    

        color_data = conn.execute(text("SELECT product_id, color FROM availablecolors")).fetchall()
        size_data = conn.execute(text("SELECT product_id, size FROM availablesizes")).fetchall()
        image_data = conn.execute(text("SELECT product_id, image_url FROM productimages")).fetchall()

    color_map = {}
    size_map = {}
    image_map = {}

    for row in color_data:
        color_map.setdefault(row.product_id, []).append(row.color)

    for row in size_data:
        size_map.setdefault(row.product_id, []).append(row.size)

    for row in image_data:
        image_map.setdefault(row.product_id, []).append(row.image_url)

    product_list = []
    for p in products:
        product_list.append({
            'product_id': p.product_id,
            'title': p.title,
            'description': p.description,
            'warranty': p.warranty_period,
            'vendor': p.vendor_name,
            'colors': color_map.get(p.product_id, []),
            'sizes': size_map.get(p.product_id, []),
            'images': image_map.get(p.product_id, [])
        })

    return render_template('products.html', products=product_list)



@app.route('/search-products', methods=['GET', 'POST'])
def search_product():
    searched_product = request.form.get('search-bar')
    
    print(f'raw search {searched_product}')
    
    if searched_product is None or searched_product == '':
        searched_product = 'blank'

    return redirect(url_for('view_products', search=searched_product))



from datetime import datetime

@app.route('/product/<int:product_id>', methods=['GET', 'POST'])
def view_product(product_id):
    with engine.connect() as conn:
        product = conn.execute(text("""
            SELECT p.*, u.username AS vendor
            FROM products p
            JOIN users u ON p.vendor_id = u.user_id
            WHERE p.product_id = :pid
        """), {'pid': product_id}).mappings().first()

        if not product:
            return "Product not found", 404

        variants = conn.execute(text("""
            SELECT v.variant_id, c.color, s.size, v.price, v.inventory_count, 
                   v.discount_price, v.discount_end_date
            FROM productvariants v
            JOIN availablecolors c ON v.color_id = c.color_id
            JOIN availablesizes s ON v.size_id = s.size_id
            WHERE v.product_id = :pid
        """), {'pid': product_id}).mappings().all()

        images = conn.execute(text("""
            SELECT image_url FROM productimages WHERE product_id = :pid
        """), {'pid': product_id}).scalars().all()

    return render_template(
        'viewProduct.html',
        product=product,
        variants=variants,
        images=images,
        now=datetime.now()
    )




@app.route('/manage-products')
def manage_products():
    user = get_logged_in_user()  

    if user is None:
        return redirect('/login') 

    user_id = user['user_id']
    role = user['user_type']  

    with engine.connect() as conn:
        if role == 'admin':
            products_query = text("SELECT * FROM products")
            products_result = conn.execute(products_query).mappings().fetchall()
        elif role == 'vendor':
            products_query = text("SELECT * FROM products WHERE vendor_id = :uid")
            products_result = conn.execute(products_query, {'uid': user_id}).mappings().fetchall()
        else:
            return redirect('/home') 

        products = []
        for product in products_result:
            product_id = product['product_id']


            colors = conn.execute(
                text("SELECT color FROM availablecolors WHERE product_id = :pid"),
                {'pid': product_id}
            ).mappings().fetchall()

            sizes = conn.execute(
                text("SELECT size FROM availablesizes WHERE product_id = :pid"),
                {'pid': product_id}
            ).mappings().fetchall()

            products.append({
                'product_id': product_id,
                'title': product['title'],
                'description': product['description'],
                'warranty_period': product['warranty_period'],
                'colors': [c['color'] for c in colors],
                'sizes': [s['size'] for s in sizes]
            })

    return render_template('manageProducts.html', products=products)



@app.route('/edit-product/<int:product_id>', methods=['GET'])
def edit_product(product_id):
    user = get_logged_in_user()
    if not user:
        return redirect('/login')

    with engine.connect() as conn:
        query = text("SELECT * FROM products WHERE product_id = :pid")
        product = conn.execute(query, {'pid': product_id}).mappings().first()

        if not product:
            return "Product not found", 404

        if user['user_type'] == 'vendor' and product['vendor_id'] != user['user_id']:
            return "Unauthorized", 403

        colors = conn.execute(text("""
            SELECT color FROM availablecolors WHERE product_id = :pid
        """), {'pid': product_id}).scalars().all()

        sizes = conn.execute(text("""
            SELECT size FROM availablesizes WHERE product_id = :pid
        """), {'pid': product_id}).scalars().all()

        images = conn.execute(text("""
            SELECT image_url FROM productimages WHERE product_id = :pid
        """), {'pid': product_id}).scalars().all()

        variants = conn.execute(text("""
            SELECT 
                v.variant_id,
                c.color,
                s.size,
                v.inventory_count,
                v.price,
                v.discount_price,
                v.discount_end_date
            FROM productvariants v
            JOIN availablecolors c ON v.color_id = c.color_id
            JOIN availablesizes s ON v.size_id = s.size_id
            WHERE v.product_id = :pid
        """), {'pid': product_id}).mappings().all()

    return render_template(
        'editProduct.html',
        product=product,
        colors=colors,
        sizes=sizes,
        images=images,
        variants=variants
    )



@app.route('/update-variants/<int:product_id>', methods=['POST'])
def update_variants(product_id):
    user = get_logged_in_user()

    if not user:
        return redirect('/login')

    with engine.begin() as conn:
        query = text("""
            SELECT * FROM products WHERE product_id = :pid
        """)
        product = conn.execute(query, {'pid': product_id}).mappings().first()

        if not product:
            return "Product not found", 404

        if user['user_type'] == 'vendor' and product['vendor_id'] != user['user_id']:
            return "Unauthorized", 403

        variants_query = text("""
            SELECT pv.variant_id, pv.price, pv.inventory_count, pv.discount_price, pv.discount_end_date,
                   c.color, s.size
            FROM productvariants pv
            JOIN availablecolors c ON pv.color_id = c.color_id
            JOIN availablesizes s ON pv.size_id = s.size_id
            WHERE pv.product_id = :pid
        """)

        variants = conn.execute(variants_query, {'pid': product_id}).mappings().all()

        for variant in variants:
            variant_id = variant['variant_id']

            price = request.form.get(f'price_{variant_id}')
            inventory = request.form.get(f'inventory_{variant_id}')
            discount_price = request.form.get(f'discount_price_{variant_id}')
            discount_end_date = request.form.get(f'discount_end_{variant_id}')

            conn.execute(text("""
                UPDATE productvariants
                SET price = :price, inventory_count = :inventory, discount_price = :discount_price, discount_end_date = :discount_end_date
                WHERE variant_id = :variant_id
            """), {
                'price': price,
                'inventory': inventory,
                'discount_price': discount_price if discount_price else None,
                'discount_end_date': discount_end_date if discount_end_date else None,
                'variant_id': variant_id
            })

    return redirect(url_for('manage_products'))



@app.route('/delete-product/<int:product_id>', methods=['POST'])
def delete_product(product_id):
    user = get_logged_in_user()
    if not user:
        return redirect('/login')

    try:
        if user['user_type'] == 'vendor':
            with engine.connect() as conn:
                product = conn.execute(
                    text("SELECT vendor_id FROM products WHERE product_id = :pid"),
                    {'pid': product_id}
                ).mappings().fetchone()

                if not product or product['vendor_id'] != user['user_id']:
                    return redirect('/manage-products')

        with engine.begin() as conn:
            conn.execute(text("DELETE FROM productvariants WHERE product_id = :pid"), {'pid': product_id})
            conn.execute(text("DELETE FROM availablecolors WHERE product_id = :pid"), {'pid': product_id})
            conn.execute(text("DELETE FROM availablesizes WHERE product_id = :pid"), {'pid': product_id})
            conn.execute(text("DELETE FROM products WHERE product_id = :pid"), {'pid': product_id})

        return redirect('/manage-products')

    except Exception as e:
        print(f"Error deleting product {product_id}: {e}")
        return redirect('/manage-products')



@app.route('/cart')
def view_cart():
    user = get_logged_in_user() 
    if not user:
        return redirect(url_for('login'))  

    with engine.connect() as conn:
        cart_items = conn.execute(text("""
            SELECT
                c.cart_id,
                p.title AS product_name,
                c.quantity,
                CASE
                    WHEN v.discount_price IS NOT NULL AND v.discount_price < v.price THEN (v.price - v.discount_price)
                    ELSE v.price
                END AS price,
                CASE
                    WHEN v.discount_price IS NOT NULL AND v.discount_price < v.price THEN (c.quantity * (v.price - v.discount_price))
                    ELSE (c.quantity * v.price)
                END AS subtotal,
                co.color,
                s.size
            FROM cart c
            JOIN productvariants v ON c.variant_id = v.variant_id
            JOIN products p ON v.product_id = p.product_id
            JOIN availablecolors co ON v.color_id = co.color_id
            JOIN availablesizes s ON v.size_id = s.size_id
            WHERE c.user_id = :uid
        """), {'uid': user['user_id']}).mappings().all()

    total = sum(item['subtotal'] for item in cart_items)

    return render_template('cart.html', cart_items=cart_items, total=total)




@app.route('/add-to-cart/<int:product_id>/<int:variant_id>', methods=['POST'])
def add_to_cart(product_id, variant_id):
    user = get_logged_in_user()
    
    if not user:
        return redirect('/login')

    quantity = int(request.form.get('quantity'))


    with engine.begin() as conn:
        variant = conn.execute(text("""
            SELECT variant_id, price, inventory_count FROM productvariants
            WHERE product_id = :pid AND variant_id = :vid
        """), {'pid': product_id, 'vid': variant_id}).mappings().first()

        if not variant:
            return "Variant not found", 400

        if quantity > variant['inventory_count']:
            return "Not enough stock available", 400

        conn.execute(text("""
            INSERT INTO cart (user_id, variant_id, quantity, price)
            VALUES (:uid, :vid, :qty, :price)
        """), {
            'uid': user['user_id'],
            'vid': variant['variant_id'],
            'qty': quantity,
            'price': variant['price']
        })


    return redirect(url_for('view_product', product_id=product_id))




@app.route('/remove-from-cart/<int:cart_id>', methods=['POST'])
def remove_from_cart(cart_id):
    user = get_logged_in_user()
    if not user:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': 'Not logged in'}), 401
        return redirect('/login')

    with engine.begin() as conn:
        conn.execute(text("""
            DELETE FROM cart
            WHERE cart_id = :cid AND user_id = :uid
        """), {'cid': cart_id, 'uid': user['user_id']})

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True})
    return redirect('/cart')











#Functions

# Hashing password
def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


# Function to check password
def check_password(entered_password, stored_hash):
    return bcrypt.checkpw(entered_password.encode("utf-8"), stored_hash.encode("utf-8"))


def get_logged_in_user():
    with engine.connect() as conn:
        user = conn.execute(text("SELECT * FROM users WHERE logged_in = 1 LIMIT 1")).mappings().first()
    return user if user else None

def get_product_id():
    with engine.connect() as conn:
        result = conn.execute(text('SELECT product_id FROM products ORDER BY product_id DESC LIMIT 1'))
        row = result.fetchone()
        return row[0] if row else None

# Logging out any user already logged in
def log_other_users_out(connect):
    check_logged = connect.execute(
        text('SELECT * FROM users WHERE logged_in = 1') 
    ).fetchone()

    if check_logged:
        connect.execute(
            text('UPDATE users SET logged_in = 0 WHERE logged_in = 1')
        )


def log_out_on_start():
    with engine.begin() as conn:  
        conn.execute(text('UPDATE users SET logged_in = 0'))

# Color group conversion function found online
def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def get_color_category(hex_color):
    r, g, b = hex_to_rgb(hex_color)
    
    import colorsys
    h, s, v = colorsys.rgb_to_hsv(r/255, g/255, b/255)
    h = h * 360  
    s = s * 100
    v = v * 100

    if v < 20:
        return 'black'
    elif s < 20 and v > 80:
        return 'white'
    elif s < 25:
        return 'grey'
    
    if h < 15 or h >= 345:
        return 'red'
    elif 15 <= h < 45:
        return 'orange'
    elif 45 <= h < 65:
        return 'yellow'
    elif 65 <= h < 170:
        return 'green'
    elif 170 <= h < 255:
        return 'blue'
    elif 255 <= h < 290:
        return 'purple'
    elif 290 <= h < 345:
        return 'pink'
    
    return 'other'


if __name__ == '__main__': 
    log_out_on_start()
    app.run(debug = True)