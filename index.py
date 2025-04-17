from flask import Flask, render_template, request, redirect, url_for, jsonify
from sqlalchemy import create_engine, text
import bcrypt
import math

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
        
        if color in color_list:
            rows = math.ceil(len(color_list) / 12)

            return render_template('productCreate.html', step_one_creation_submit=True, color_list=color_list, rows=range(rows))
        else:
            rows = math.ceil(len(color_list) / 12)

            color_list.append(color)

            return render_template('productCreate.html', step_one_creation_submit=True, color_list=color_list, rows=range(rows))

 
        
        

        # try:
        #     with engine.begin() as conn:
        #         conn.execute(
        #             text('INSERT INTO availablecolors (product_id,  color,)'), {'product_id':user['user_id], 'color':color })
        #     return render_template('productCreate.html', step_two_creation_submit=True)
        # except:
        #     return render_template('productCreate.html, step_two_creation_submit=False)
        
@app.route('/remove-color', methods=['GET', 'POST'])
def remove_color():
    color = request.args.get('color')
    global color_list
    
    print(f'The color is {color}')
    print(f'current list {color_list}')
    
    if color in color_list:
        color_list.remove(color)
        print('color removed')
        
    print(f'updated list {color_list}')
        
    return render_template("productCreate.html", color_list=color_list, step_one_creation_submit=True)

            


# @app.route('size-submit', methods=['GET', 'POST'])
# def size_submit():
#     user = get_logged_in_user()
#     if not user:
#         return redirect(url_for('login'))

#     selected_sizes = []

#     for size in ['xsmall', 'small', 'medium', 'large', 'xlarge']:
#         if request.form.get(size):
#             selected_sizes.append(size)

#     try:
#         with engine.begin() as conn:
#             result = conn.execute(
#                 text('SELECT product_id FROM products WHERE vendor_id = :vendor_id ORDER BY product_id DESC LIMIT 1'),
#                 {'vendor_id': user['user_id']}
#             )
#             product = result.mappings().first()
#             if product:
#                 for size in selected_sizes:
#                     conn.execute(
#                         text('INSERT INTO availablesizes (product_id, size) VALUES (:product_id, :size)'),
#                         {'product_id': product['product_id'], 'size': size}
#                     )

#                 # Optionally fetch and return size list to display it
#                 size_result = conn.execute(
#                     text('SELECT size FROM availablesizes WHERE product_id = :product_id'),
#                     {'product_id': product['product_id']}
#                 )
#                 size_list = [row['size'] for row in size_result]

#                 return render_template('productCreate.html', step_three_creation_submit=True, size_list=size_list)
#     except:
#         return render_template('productCreate.html', step_three_creation_submit=False)

#     return render_template('productCreate.html', step_three_creation_submit=True)




@app.route('/chat', methods=['GET', 'POST'])
def chat():
    user = get_logged_in_user()
    if not user:
        return redirect(url_for('home'))

    if request.method == 'GET':
        vendor_id = request.args.get('vendor_id')
        if not vendor_id:
            return redirect(url_for('home'))

        with engine.begin() as conn:
            messages = conn.execute(text("""
                SELECT * FROM chat
                WHERE (sender_id = :user_id AND receiver_id = :vendor_id)
                   OR (sender_id = :vendor_id AND receiver_id = :user_id)
                ORDER BY sent_at ASC
            """), {'user_id': user['user_id'], 'vendor_id': vendor_id}).fetchall()

        return render_template('chat.html', messages=messages, user=user, vendor_id=vendor_id)

    elif request.method == 'POST':
        message = request.form.get('message')
        receiver_id = request.form.get('vendor_id')

        if message and receiver_id:
            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO chat (sender_id, receiver_id, message)
                    VALUES (:sender_id, :receiver_id, :message)
                """), {'sender_id': user['user_id'], 'receiver_id': receiver_id, 'message': message})

        return redirect(url_for('chat', vendor_id=receiver_id))


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