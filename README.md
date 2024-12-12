# README

## Overview
This project provides a framework for generating database queries dynamically based on configurations. It includes a Python script (`generator.py`) for generating SQL insert and delete queries and a configuration file (`config.json`) that defines database connection parameters, query templates, and additional settings.

## Files

### 1. `config.json`
This file contains the configuration data required for the query generation process, including:

- **Databases**: Connection details for multiple databases, including `host`, `database`, `user`, and `password`.
- **Query Definitions**: Templates for queries associated with specific tables, including conditions, rollback conditions, excluded columns, and output file names.
- **Ordered Tables**: A prioritized list of tables to ensure proper dependency handling during query generation.
- **Excluded Tables**: Tables where specific actions (e.g., `DO NOTHING` or `DO NOT DELETE`) should be applied.

### 2. `generator.py`
This Python script implements the logic for query generation and saving. Key components include:

- **`load_config`**: Loads configuration from a JSON file.
- **`connect_db`**: Establishes a connection to the database.
- **`generate_insert_query`**: Dynamically creates SQL insert queries.
- **`generate_delete_query`**: Dynamically creates SQL delete queries.
- **`execute_and_save_queries`**: Executes the generated queries and writes them to output files.
- **`main`**: The entry point of the script that drives the entire process, including reading configurations, querying the database, and generating query files.

## How to Use

1. **Prepare the Configuration File**
   - Ensure that `config.json` contains valid database connection details and query templates.
   - Update the ordered tables and excluded tables sections as needed.

2. **Run the Script**
   - Execute the script by providing a `service_code` as an argument.
     ```bash
     python generator.py <service_code>
     ```
   - The script will:
     - Validate the provided service code.
     - Query the database for related data.
     - Generate SQL insert and delete queries.
     - Save the generated queries in a timestamped directory within the `generated` folder.

3. **Check the Output**
   - Generated SQL files will be located in the output directory.
   - Rollback files are also created to revert the generated SQL changes if necessary.

## Example

### Configuration Example (`config.json`):
```json
{
    "databases": {
        "config": {
            "host": "10.23.96.72",
            "database": "config-service",
            "user": "config",
            "password": "example"
        }
    },
    "queries": {
        "config_queries": [
            {
                "table_name": "forms",
                "condition": "id = %s",
                "params": ["formId"],
                "output_file": "forms.sql"
            }
        ]
    }
}
```

### Script Execution:
```bash
python generator.py demo_service_code
```

### Output:
Generated SQL files will include:
- Insert statements for specified tables.
- Corresponding rollback queries.

## Prerequisites

- Python 3.x
- Required Python packages: `psycopg2`
- PostgreSQL database

## Logging
The script logs its actions to the console, including errors and status updates, for easier debugging and monitoring.

## Notes
- Ensure sensitive data, such as database credentials, is secured and not hardcoded in the files.
- Use appropriate permissions for generated files and restrict access to sensitive information.

