import os
import sys
import json
import logging
from datetime import datetime
import psycopg2

# Ensure UTF-8 encoding
if hasattr(sys, 'setdefaultencoding'):
    sys.setdefaultencoding('utf-8')

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_config(config_path):
    """Load configuration from a JSON file."""
    with open(config_path, 'r') as file:
        return json.load(file)

def connect_db(db_params):
    """Establish a connection to the database."""
    conn = psycopg2.connect(**db_params)
    conn.set_client_encoding('UTF8')  # Set UTF8 encoding for the connection
    return conn

def check_table_exists(cursor, table_name):
    """Check if a table exists in the database."""
    cursor.execute("""
        SELECT EXISTS (
            SELECT 1 
            FROM information_schema.tables 
            WHERE table_name = %s
        );
    """, (table_name,))
    return cursor.fetchone()[0]

def get_table_columns(cursor, table_name, exclude_columns):
    """Retrieve column names for a table, excluding specified columns."""
    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = %s
        ORDER BY ordinal_position
    """, (table_name,))
    return [row[0] for row in cursor.fetchall() if row[0] not in exclude_columns]

def generate_insert_query(cursor, table_name, condition, params, exclude_columns, exculded_do_nothing_tables):
    """Generate a dynamic INSERT query."""
    if not check_table_exists(cursor, table_name):
        raise ValueError(f"Table '{table_name}' does not exist in the database.")
    
    columns = get_table_columns(cursor, table_name, exclude_columns)
    insert_query = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ("
    values_query = " || ', ' || ".join([
        f"COALESCE(quote_literal({col}), 'NULL')" if col != 'id' else f"COALESCE({col}::text, 'NULL')" 
        for col in columns
    ])
    
    if table_name in exculded_do_nothing_tables:
        update_query = ", ".join([f"{col} = EXCLUDED.{col}" for col in columns if col != 'id'])
        final_query = f"""
            SELECT '{insert_query}' || {values_query} || ') ON CONFLICT (id) DO UPDATE SET {update_query};'
            FROM {table_name} WHERE {condition};
        """
    else:
        final_query = f"""
            SELECT '{insert_query}' || {values_query} || ') ON CONFLICT (id) DO NOTHING;'
            FROM {table_name} WHERE {condition};
        """
    
    cursor.execute(final_query, params)
    return cursor.fetchall()

def generate_delete_query(table_name, condition, params):
    """Generate a dynamic DELETE query."""
    delete_query = f"DELETE FROM {table_name} WHERE {condition};"
    delete_statement = delete_query % tuple([f"'{param}'" if isinstance(param, str) else param for param in params])
    return [(delete_statement,)]

def execute_and_save_queries(db_conn_params, queries, output_dir, params_dict, ordered_tables, exculded_do_nothing_tables, exculded_delete_tables):
    """Execute and save generated queries to files."""
    rollback_file = os.path.join(output_dir, f"rollback_{db_conn_params['database']}_{params_dict['code']}.sql")
    output_file = os.path.join(output_dir, f"{db_conn_params['database']}_insert_statements.sql")

    insert_file_empty = not os.path.exists(output_file) or os.stat(output_file).st_size == 0

    rollback_queries = {table: [] for table in ordered_tables}
    rollback_queries_other = []

    conn = connect_db(db_conn_params)
    cursor = conn.cursor()

    for query_info in queries:
        table_name = query_info["table_name"]
        condition = query_info["condition"]
        params = [params_dict.get(param, param) for param in query_info["params"]]
        exclude_columns = query_info.get("exclude_columns", [])
        like_condition = query_info.get("like_condition", False)

        if like_condition:
            params = [f"%{param}%" for param in params]

        try:
            results = generate_insert_query(cursor, table_name, condition, params, exclude_columns, exculded_do_nothing_tables)
            if results:
                # Generate and write delete statements only if there are insert statements
                delete_statements = []
                if table_name not in exculded_delete_tables:
                    delete_statements = generate_delete_query(table_name, condition, params)
                    with open(output_file, "a", encoding='utf-8') as file:
                        if insert_file_empty:
                            file.write("\n-- Deleting from table: {}\n".format(table_name))
                        for row in delete_statements:
                            file.write(row[0])
                            file.write("\n")
                        file.write("\n")  # Add space after delete statements

                # Generate and write insert statements
                with open(output_file, "a", encoding='utf-8') as file:
                    file.write("-- Inserting into table: {}\n".format(table_name))
                    for row in results:
                        file.write(row[0])
                        file.write("\n")
                    file.write("\n")  # Add space after insert statements

                # Generate rollback delete queries
                for row in delete_statements:
                    if table_name in ordered_tables:
                        rollback_queries[table_name].append(row[0])
                    else:
                        rollback_queries_other.append(row[0])

                logger.info("%s: Insert and delete/update statements appended to %s", table_name, output_file)
            else:
                logger.info("No insert statements generated for table: %s", table_name)

        except Exception as e:
            logger.error("Error processing table %s: %s", table_name, e)

    cursor.close()
    conn.close()

    # Write rollback queries in the specified order
    with open(rollback_file, "a", encoding='utf-8') as file:  # Ensure UTF-8 encoding when writing to file
        for table in ordered_tables:
            if rollback_queries[table]:
                file.write(f"-- Rollback for table: {table}\n")
                for query in rollback_queries[table]:
                    file.write(query)
                    file.write("\n")
        for query in rollback_queries_other:
            file.write(query)
            file.write("\n")

def main():
    if len(sys.argv) != 2:
        print("Usage: python generator.py service_code")
        sys.exit(1)

    code = sys.argv[1]
    config = load_config('config.json')

    databases = config.get("databases", {})
    queries = config.get("queries", {})
    ordered_tables = config.get("ordered_tables", [])
    exculded_do_nothing_tables = config.get("exculded_do_nothing_tables", [])
    exculded_delete_tables = config.get("exculded_delete_tables", [])

    if not databases or not queries or not ordered_tables:
        logger.error("Configuration is missing required sections.")
        sys.exit(1)

    config_conn = connect_db(databases["config"])
    cur = config_conn.cursor()

    service_query = """
        SELECT id FROM services
        WHERE code = %s 
        AND deleted_at IS NULL
    """
    cur.execute(service_query, (code,))
    row = cur.fetchone()

    if row:
        serviceId = row[0]
        logger.info("Service ID: %s", serviceId)
    else:
        logger.error("No service found for code: %s", code)
        sys.exit(1)

    form_query = """
        SELECT id FROM forms 
        WHERE service = %s 
        AND deleted_at IS NULL
    """
    cur.execute(form_query, (serviceId,))
    row = cur.fetchone()

    if row:
        formId = row[0]
        logger.info("Form ID: %s", formId)
    else:
        logger.error("No form found for service ID: %s", serviceId)
        sys.exit(1)

    current_datetime = datetime.now().strftime("%Y%m%d%H%M")
    output_dir = os.path.join(os.getcwd(), f"generated/generated_{current_datetime}_{code}")

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    try:
        params_dict = {
            "code": code,
            "formId": formId,
            "serviceId": serviceId
        }

        for db_key, db_queries in queries.items():
            db_name = db_key.split('_')[0]
            db_conn_params = databases.get(db_name)
            if not db_conn_params:
                logger.error("Database connection parameters not found for '%s'", db_key)
                continue

            execute_and_save_queries(db_conn_params, db_queries, output_dir, params_dict, ordered_tables, exculded_do_nothing_tables, exculded_delete_tables)

    except Exception as error:
        logger.error("Error while processing: %s", error)

    finally:
        if config_conn:
            config_conn.close()

if __name__ == "__main__":
    main()
