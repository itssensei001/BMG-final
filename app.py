from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
import pymysql
import os
import json

app = Flask(__name__, static_url_path='', static_folder='static')
CORS(app)  # This allows cross-origin requests

# Database connection
def get_db_connection():
    connection = pymysql.connect(
        host='localhost',
        user='root',
        password='EddieOliver..1',
        db='bmg_vacations',
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )
    return connection

@app.route('/api/properties')
def get_properties():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT * FROM properties')
            properties = cursor.fetchall()
            return jsonify(properties)
    finally:
        conn.close()

# Serve static files (HTML, CSS, JS)
@app.route('/')
def index():
    return app.send_static_file('home.html')

@app.route('/properties.html')
def properties():
    return app.send_static_file('properties.html')

@app.route('/property.html')
def property_detail():
    return app.send_static_file('property_template.html')

@app.route('/api/property/<int:property_id>')
def get_property(property_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Get basic property info
            cursor.execute('SELECT * FROM properties WHERE id = %s', (property_id,))
            property_data = cursor.fetchone()
            
            if not property_data:
                return jsonify({"error": "Property not found"}), 404
            
            # Get features
            cursor.execute('SELECT feature FROM property_features WHERE property_id = %s', (property_id,))
            features = [row['feature'] for row in cursor.fetchall()]
            
            # Get images
            cursor.execute('SELECT url, alt_text FROM property_images WHERE property_id = %s', (property_id,))
            gallery_images = [{"url": row['url'], "alt": row['alt_text']} for row in cursor.fetchall()]
            
            # Complete response - Ensure all needed fields are explicitly included
            result = {
                "id": property_data['id'],
                "name": property_data['name'],
                "title": property_data.get('title', property_data['name']), # Use get for safety
                "location": property_data['location'],
                "description": property_data.get('description', ''),
                "image_url": property_data['image_url'], # *** ADD THIS LINE EXPLICITLY ***
                "hero_image": property_data.get('hero_image', property_data['image_url']), # Use get
                "main_image": property_data.get('main_image', property_data['image_url']), # Use get
                "page_url": property_data.get('page_url',''), # Use get
                "price_per_night": property_data.get('price_per_night', 0), # Use get
                "currency": property_data.get('currency', 'KES'), # Use get
                "max_occupancy": property_data.get('max_occupancy', 2), # Use get
                "features": features,
                "gallery_images": gallery_images
            }
            
            return jsonify(result)
    except Exception as e:
         print(f"Error fetching property {property_id}: {e}")
         return jsonify({"error": "Database error fetching property details"}), 500
    finally:
        conn.close()

# Route to serve the admin page
@app.route('/admin')
def admin_page():
    # You might want to add authentication here later
    return app.send_static_file('admin.html')

# GET all properties (for admin table view)
@app.route('/api/admin/properties', methods=['GET'])
def get_admin_properties():
    # Add authentication check here
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT id, name, location, price_per_night, currency FROM properties ORDER BY id')
            properties = cursor.fetchall()
            return jsonify(properties)
    except Exception as e:
        print(f"Error fetching admin properties: {e}")
        return jsonify({"error": "Database error"}), 500
    finally:
        conn.close()

# POST to add a new property (Revised INSERT logic)
@app.route('/api/admin/properties', methods=['POST'])
def add_property():
    # Add authentication check here
    data = request.get_json()
    details = data.get('details', {})
    features = data.get('features', [])
    gallery = data.get('gallery', [])

    if not all(k in details for k in ('name', 'title', 'location', 'image_url', 'price_per_night')):
         return jsonify({"error": "Missing required property details"}), 400
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # --- Step 1: Insert into properties table WITH a temporary page_url ---
            sql_prop = """
            INSERT INTO properties (
                name, title, location, description, image_url, hero_image, 
                main_image, price_per_night, currency, max_occupancy, page_url 
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) 
            """
            # Add a temporary placeholder that won't be used long
            temp_page_url = "pending" 
            
            cursor.execute(sql_prop, (
                details['name'], details['title'], details['location'], details.get('description'),
                details['image_url'], details.get('hero_image', details['image_url']), 
                details.get('main_image', details['image_url']),
                details['price_per_night'], details.get('currency', 'KES'), 
                details.get('max_occupancy', 2),
                temp_page_url # Include the placeholder
            ))
            
            # --- Step 2: Get the ID of the row just inserted ---
            property_id = cursor.lastrowid 
            if not property_id:
                 raise Exception("Failed to get last inserted ID.") # Should not happen typically

            # --- Step 3: Update the page_url with the correct value using the ID ---
            page_url = f"property.html?id={property_id}"
            cursor.execute("UPDATE properties SET page_url = %s WHERE id = %s", (page_url, property_id))
            
            # --- Step 4: Insert features (if any) ---
            if features:
                feature_values = [(property_id, feature) for feature in features]
                cursor.executemany("INSERT INTO property_features (property_id, feature) VALUES (%s, %s)", feature_values)

            # --- Step 5: Insert gallery images (if any) ---
            if gallery:
                gallery_values = [(property_id, img['url'], img.get('alt')) for img in gallery]
                cursor.executemany("INSERT INTO property_images (property_id, url, alt_text) VALUES (%s, %s, %s)", gallery_values)

            # --- Step 6: Commit the transaction ---
            conn.commit() 
            return jsonify({"message": "Property added successfully", "property_id": property_id}), 201
            
    except pymysql.Error as db_err: # Catch specific DB errors
         conn.rollback() # Rollback changes on error
         print(f"Database error adding property: {db_err}") # Log specific DB error
         # Provide a more informative error back to the frontend
         return jsonify({"error": f"Database Error: {db_err}"}), 500
    except Exception as e:
        conn.rollback() # Rollback changes on error
        print(f"Error adding property: {e}") # Log general error
        return jsonify({"error": "An unexpected error occurred while adding property"}), 500
    finally:
        if conn: # Ensure connection is closed even if error happened before assignment
            conn.close()

# PUT to update an existing property (Modified for Partial Updates)
@app.route('/api/admin/properties/<int:property_id>', methods=['PUT'])
def update_property(property_id):
    # Add authentication check here
    data = request.get_json()
    details = data.get('details', {})
    features = data.get('features') # Use get to allow omitting features/gallery
    gallery = data.get('gallery')   # Use get

    if not details: # Ensure at least some details are provided for update
         return jsonify({"error": "No update data provided"}), 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            
            # --- Dynamically build UPDATE statement for properties table ---
            update_fields = []
            update_values = []
            # Map frontend keys to database columns if they differ, otherwise use key directly
            field_map = { 
                # Add mappings if frontend keys don't match DB columns exactly
                # 'frontend_key': 'db_column_name', 
            }

            for key, value in details.items():
                # Basic security: ensure key is likely a valid column name 
                # (adjust whitelist as needed)
                allowed_keys = ['name', 'title', 'location', 'description', 'image_url', 
                                'hero_image', 'main_image', 'price_per_night', 
                                'currency', 'max_occupancy']
                db_column = field_map.get(key, key) # Get mapped column name or use key
                
                if db_column in allowed_keys:
                    update_fields.append(f"{db_column} = %s")
                    update_values.append(value)
                else:
                    print(f"Warning: Ignoring unknown field '{key}' during update.")


            if not update_fields:
                 return jsonify({"error": "No valid fields provided for update"}), 400

            update_values.append(property_id) # Add the ID for the WHERE clause
            sql_update_prop = f"UPDATE properties SET {', '.join(update_fields)} WHERE id = %s"
            
            print(f"Executing SQL: {sql_update_prop}") # Debugging
            print(f"With values: {update_values}")    # Debugging
            
            cursor.execute(sql_update_prop, tuple(update_values))
            # ---------------------------------------------------------------

            # --- Update Features (Only if 'features' array is present in request) ---
            # This still uses delete/insert, but only if the frontend sends the features array
            if features is not None: # Check if features array was provided
                print(f"Updating features for property {property_id}") # Debugging
                cursor.execute("DELETE FROM property_features WHERE property_id = %s", (property_id,))
                if features: # Only insert if the list is not empty
                    feature_values = [(property_id, feature) for feature in features]
                    cursor.executemany("INSERT INTO property_features (property_id, feature) VALUES (%s, %s)", feature_values)

            # --- Update Gallery Images (Only if 'gallery' array is present in request) ---
            # This still uses delete/insert
            if gallery is not None: # Check if gallery array was provided
                print(f"Updating gallery for property {property_id}") # Debugging
                cursor.execute("DELETE FROM property_images WHERE property_id = %s", (property_id,))
                if gallery: # Only insert if the list is not empty
                     gallery_values = [(property_id, img['url'], img.get('alt')) for img in gallery]
                     cursor.executemany("INSERT INTO property_images (property_id, url, alt_text) VALUES (%s, %s, %s)", gallery_values)

            conn.commit()
            return jsonify({"message": f"Property {property_id} updated successfully"}), 200

    except pymysql.Error as db_err: # Catch specific DB errors
         conn.rollback()
         print(f"Database error updating property {property_id}: {db_err}")
         return jsonify({"error": f"Database error: {db_err}"}), 500
    except Exception as e:
        conn.rollback()
        print(f"Error updating property {property_id}: {e}")
        return jsonify({"error": "An unexpected error occurred during update"}), 500
    finally:
        conn.close()

# DELETE a property
@app.route('/api/admin/properties/<int:property_id>', methods=['DELETE'])
def delete_property_api(property_id):
    # Add authentication check here
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # The ON DELETE CASCADE in the DB schema *should* handle features/images, 
            # but explicit deletes are safer if cascade isn't set or guaranteed.
            # cursor.execute("DELETE FROM property_features WHERE property_id = %s", (property_id,))
            # cursor.execute("DELETE FROM property_images WHERE property_id = %s", (property_id,))
            
            # Delete the main property record
            rows_affected = cursor.execute("DELETE FROM properties WHERE id = %s", (property_id,))
            
            if rows_affected == 0:
                 return jsonify({"error": "Property not found"}), 404

            conn.commit()
            return jsonify({"message": f"Property {property_id} deleted successfully"}), 200

    except Exception as e:
        conn.rollback()
        print(f"Error deleting property {property_id}: {e}")
        return jsonify({"error": "Database error occurred during deletion"}), 500
    finally:
        conn.close()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
