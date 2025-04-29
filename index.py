from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from sqlalchemy import create_engine, text
import bcrypt
import math
import traceback
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

# , incoming_chats=incoming_chats

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


# @app.route('products', methods = ['GET', 'POST'])
# def products():


@app.route('/product-create', methods=['GET', 'POST'])
def product_create():
    user = get_logged_in_user()
    
    if request.method == "POST":
        name = request.form.get('product-name')
        description = request.form.get('product-description')
        warranty_period = request.form.get('warranty-period')
        category = request.form.get('category')
        
        try:
            with engine.begin() as conn:
                conn.execute(text('INSERT INTO products (title, description, warranty_period, category, vendor_id) VALUES (:title, :description, :warranty, :category, :vendor_id)'),
                             {'title':name, 'description':description, 'warranty':warranty_period, 'category':category.lower(), 'vendor_id':user['user_id']})
                
            return render_template('productCreate.html', step_one_creation_submit=True)
        except:
            return render_template('productCreate.html', step_one_creation_submit=False)
        
    return render_template('productCreate.html')



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
                conn.execute(
                    text('INSERT INTO availablecolors (product_id, color) VALUES (:product_id, :color)'),
                    {'product_id': product_id, 'color': color}
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


@app.route('/view-products')
def view_products():
    with engine.connect() as conn:
        products = conn.execute(text("""
            SELECT p.product_id, p.title, p.description, p.warranty_period
            FROM products p
        """)).fetchall()

        color_data = conn.execute(text("""
            SELECT product_id, color
            FROM availablecolors
        """)).fetchall()

        size_data = conn.execute(text("""
            SELECT product_id, size
            FROM availablesizes
        """)).fetchall()

        image_data = conn.execute(text("""
            SELECT product_id, image_url
            FROM productimages
        """)).fetchall()

    color_map = {}
    for row in color_data:
        color_map.setdefault(row.product_id, []).append(row.color)

    size_map = {}
    for row in size_data:
        size_map.setdefault(row.product_id, []).append(row.size)

    image_map = {}
    for row in image_data:
        image_map.setdefault(row.product_id, []).append(row.image_url)

    product_list = []
    for p in products:
        product_list.append({
            'product_id': p.product_id,
            'title': p.title,
            'description': p.description,
            'warranty': p.warranty_period,
            'colors': color_map.get(p.product_id, []),
            'sizes': size_map.get(p.product_id, []),
            'images': image_map.get(p.product_id, [])
        })

    return render_template('products.html', products=product_list)






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


if __name__ == '__main__': 
    log_out_on_start()
    app.run(debug = True)