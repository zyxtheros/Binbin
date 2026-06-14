import os
import json
import psycopg2
import psycopg2.extras
from flask import Flask, render_template, request, redirect, url_for, abort, Response
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

def get_db():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", 5432),
        dbname=os.getenv("DB_NAME", "Inventory"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "super"),
        cursor_factory=psycopg2.extras.RealDictCursor
    )


# ---------- Home: list all items ----------
@app.route("/")
def index():
    conn = get_db()
    cur = conn.cursor()

    # --- Build filter options: only fields actually used by items ---
    cur.execute("""
        SELECT DISTINCT sfd.field_key, sfd.display_name, sfd.field_type, sfd.unit, sfd.sort_order
        FROM spec_field_definitions sfd
        JOIN items i ON i.specs ? sfd.field_key
        ORDER BY sfd.sort_order, sfd.display_name
    """)
    used_fields = cur.fetchall()

    filters = []
    for f in used_fields:
        if f["field_type"] == "number":
            # Get min/max across all items for this field
            cur.execute("""
                SELECT
                    MIN((specs ->> %s)::numeric) AS min_val,
                    MAX((specs ->> %s)::numeric) AS max_val
                FROM items
                WHERE specs ? %s AND specs ->> %s ~ '^-?[0-9]+(\.[0-9]+)?$'
            """, (f["field_key"], f["field_key"], f["field_key"], f["field_key"]))
            bounds = cur.fetchone()

            filters.append({
                "field_key": f["field_key"],
                "display_name": f["display_name"],
                "field_type": "number",
                "unit": f["unit"],
                "min_val": bounds["min_val"],
                "max_val": bounds["max_val"],
            })
        else:
            # Get distinct values for text/boolean fields
            cur.execute("""
                SELECT DISTINCT specs ->> %s AS val
                FROM items
                WHERE specs ? %s
                ORDER BY val
            """, (f["field_key"], f["field_key"]))
            values = [row["val"] for row in cur.fetchall()]

            filters.append({
                "field_key": f["field_key"],
                "display_name": f["display_name"],
                "field_type": f["field_type"],
                "unit": f["unit"],
                "options": values,
            })

    # --- Apply filters from query params ---
    conditions = []
    params = []

    for f in filters:
        key = f["field_key"]

        if f["field_type"] == "number":
            min_param = request.args.get(f"min_{key}")
            max_param = request.args.get(f"max_{key}")
            if min_param:
                conditions.append("(specs ->> %s)::numeric >= %s")
                params.extend([key, min_param])
            if max_param:
                conditions.append("(specs ->> %s)::numeric <= %s")
                params.extend([key, max_param])
        else:
            selected = request.args.getlist(key)
            if selected:
                placeholders = ", ".join(["%s"] * len(selected))
                conditions.append(f"(specs ->> %s) IN ({placeholders})")
                params.append(key)
                params.extend(selected)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    query = f"SELECT id, sku, name, description FROM items {where_clause} ORDER BY name"
    cur.execute(query, params)
    items = cur.fetchall()

    conn.close()
    return render_template("index.html", items=items, filters=filters, request=request)

# ---------- item detail page ----------
@app.route("/item/<int:item_id>")
def item(item_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT id, sku, name, description, specs FROM items WHERE id = %s", (item_id,))
    item = cur.fetchone()
    if not item:
        conn.close()
        abort(404)

    cur.execute("SELECT id, filename, is_primary FROM items_images WHERE item_id = %s", (item_id,))
    images = cur.fetchall()

    cur.execute("SELECT id, filename FROM items_datasheets WHERE item_id = %s", (item_id,))
    datasheets = cur.fetchall()

    # Pull catalog metadata for every spec key this item has
    cur.execute("""
        SELECT field_key, display_name, field_type, unit
        FROM spec_field_definitions
        ORDER BY sort_order, display_name
    """)
    all_fields = {f["field_key"]: f for f in cur.fetchall()}

    specs = item["specs"] or {}
    spec_rows = []
    for key, value in specs.items():
        meta = all_fields.get(key, {"display_name": key, "unit": None})
        spec_rows.append({
            "key": key,
            "display_name": meta["display_name"],
            "unit": meta.get("unit"),
            "value": value,
        })

    conn.close()
    return render_template(
        "item.html",
        item=item,
        images=images,
        datasheets=datasheets,
        spec_rows=spec_rows,
    )


# ---------- New item form ----------
@app.route("/item/new", methods=["GET", "POST"])
def new_item():
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        sku = request.form["sku"].strip()
        name = request.form["name"].strip()
        description = request.form.get("description", "").strip()

        # --- Build specs dict from submitted fields ---
        specs = {}

        # Existing fields selected via dropdowns
        field_keys = request.form.getlist("field_key[]")
        field_values = request.form.getlist("field_value[]")

        for key, value in zip(field_keys, field_values):
            value = value.strip()
            if not key or key == "__new__" or not value:
                continue
            specs[key] = value

        # New fields created on the fly
        new_names = request.form.getlist("new_field_name[]")
        new_values = request.form.getlist("new_field_value[]")
        new_types = request.form.getlist("new_field_type[]")
        new_units = request.form.getlist("new_field_unit[]")

        for display_name, value, ftype, unit in zip(new_names, new_values, new_types, new_units):
            display_name = display_name.strip()
            value = value.strip()
            if not display_name or not value:
                continue

            field_key = display_name.lower().replace(" ", "_")
            field_key = "".join(c for c in field_key if c.isalnum() or c == "_")
            unit = unit.strip() or None

            cur.execute("""
                INSERT INTO spec_field_definitions (field_key, display_name, field_type, unit, sort_order)
                VALUES (%s, %s, %s, %s, (SELECT COALESCE(MAX(sort_order), 0) + 10 FROM spec_field_definitions))
                ON CONFLICT (field_key) DO NOTHING
            """, (field_key, display_name, ftype or "text", unit))

            specs[field_key] = value

        # --- Insert the item ---
        cur.execute(
            "INSERT INTO items (sku, name, description, specs) VALUES (%s, %s, %s, %s::jsonb) RETURNING id",
            (sku, name, description, json.dumps(specs))
        )
        new_id = cur.fetchone()["id"]

        # --- Handle image upload ---
        image_file = request.files.get("image")
        if image_file and image_file.filename:
            image_data = image_file.read()
            cur.execute("""
                INSERT INTO items_images (item_id, filename, mime_type, data, is_primary)
                VALUES (%s, %s, %s, %s, TRUE)
            """, (new_id, image_file.filename, image_file.mimetype, psycopg2.Binary(image_data)))

        conn.commit()
        conn.close()
        return redirect(url_for("item", item_id=new_id))

    # GET — load catalog fields for the dropdown
    cur.execute("""
        SELECT field_key, display_name, field_type, unit
        FROM spec_field_definitions
        ORDER BY sort_order, display_name
    """)
    catalog_fields = cur.fetchall()
    conn.close()
    return render_template("new_item.html", catalog_fields=catalog_fields)


# ---------- Edit specs for a item (add/remove fields) ----------
@app.route("/item/<int:item_id>/specs", methods=["GET", "POST"])
def edit_specs(item_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT id, name, specs FROM items WHERE id = %s", (item_id,))
    item = cur.fetchone()
    if not item:
        conn.close()
        abort(404)

    if request.method == "POST":
        action = request.form.get("action")

        if action == "add_field":
            field_key = request.form["field_key"].strip()
            value = request.form["value"].strip()

            if field_key == "__new__":
                # User is creating a brand-new catalog field
                new_key = request.form["new_field_key"].strip().lower().replace(" ", "_")
                new_label = request.form["new_display_name"].strip()
                new_type = request.form.get("new_field_type", "text")
                new_unit = request.form.get("new_unit", "").strip() or None

                cur.execute("""
                    INSERT INTO spec_field_definitions (field_key, display_name, field_type, unit, sort_order)
                    VALUES (%s, %s, %s, %s, (SELECT COALESCE(MAX(sort_order), 0) + 10 FROM spec_field_definitions))
                    ON CONFLICT (field_key) DO NOTHING
                """, (new_key, new_label, new_type, new_unit))

                field_key = new_key

            # Merge the new value into the item's specs JSONB
            cur.execute("""
                UPDATE items
                SET specs = specs || %s::jsonb, updated_at = NOW()
                WHERE id = %s
            """, (json.dumps({field_key: value}), item_id))

        elif action == "remove_field":
            field_key = request.form["field_key"]
            cur.execute("""
                UPDATE items
                SET specs = specs - %s, updated_at = NOW()
                WHERE id = %s
            """, (field_key, item_id))

        conn.commit()
        conn.close()
        return redirect(url_for("edit_specs", item_id=item_id))

    # GET: show current specs + catalog dropdown of available fields to add
    cur.execute("""
        SELECT field_key, display_name, field_type, unit
        FROM spec_field_definitions
        ORDER BY sort_order, display_name
    """)
    all_fields = cur.fetchall()

    specs = item["specs"] or {}
    field_lookup = {f["field_key"]: f for f in all_fields}

    current_specs = []
    for key, value in specs.items():
        meta = field_lookup.get(key, {"display_name": key, "unit": None})
        current_specs.append({
            "key": key,
            "display_name": meta["display_name"],
            "unit": meta.get("unit"),
            "value": value,
        })

    # Fields not yet used on this item — available to add via dropdown
    available_fields = [f for f in all_fields if f["field_key"] not in specs]

    conn.close()
    return render_template(
        "edit_specs.html",
        item=item,
        current_specs=current_specs,
        available_fields=available_fields,
    )


# ---------- Image / PDF binary serving ----------
@app.route("/image/<int:image_id>")
def image(image_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT data, mime_type FROM items_images WHERE id = %s", (image_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        abort(404)
    return Response(bytes(row["data"]), mimetype=row["mime_type"] or "image/jpeg")


@app.route("/datasheet/<int:sheet_id>")
def datasheet(sheet_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT data, filename FROM items_datasheets WHERE id = %s", (sheet_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        abort(404)
    return Response(
        bytes(row["data"]),
        mimetype="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{row["filename"]}"'}
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)