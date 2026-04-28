import psycopg2
from django.shortcuts import render, HttpResponseRedirect
from django.http import JsonResponse
from django.conf import settings

def get_db_connection(db_name):
    try:
        conn = psycopg2.connect(
            dbname=db_name,
            user=settings.DATABASES['default']['USER'],
            password=settings.DATABASES['default']['PASSWORD'],
            host=settings.DATABASES['default']['HOST'],
            port=settings.DATABASES['default']['PORT']
        )
        return conn
    except Exception as e:
        raise Exception(f"Ошибка подключения к БД {db_name}: {str(e)}")

def main_page(request):
    databases = []
    tables = []
    
    default_db = settings.DATABASES['default']['NAME']
    
    db_from_url = request.GET.get('db')
    db_from_post = request.POST.get('selected_db')
    
    if db_from_url and db_from_url in ['postgres', 'template1']:
         current_db_name = db_from_url
    elif db_from_post:
        current_db_name = db_from_post
    elif db_from_url:
        current_db_name = db_from_url
    else:
        current_db_name = default_db

    result_msg = None
    error = None
    selected_table_data = None
    selected_table_name = None

    hidden_tables = [
        'django_migrations', 'django_content_type', 'auth_permission',
        'auth_group', 'auth_group_permissions', 'auth_user',
        'auth_user_groups', 'auth_user_user_permissions', 'django_admin_log',
        'django_session', 'cycle_app_cyclerecord'
    ]

    # --- AJAX ЗАПРОС ДЛЯ ПОЛУЧЕНИЯ СХЕМЫ ТАБЛИЦЫ (если понадобится в будущем) ---
    if request.GET.get('action') == 'get_schema':
        table_name = request.GET.get('table')
        target_db = request.GET.get('db') or current_db_name
        
        if table_name:
            try:
                conn = get_db_connection(target_db)
                cur = conn.cursor()
                cur.execute(f"""
                    SELECT column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_name = '{table_name}'
                    ORDER BY ordinal_position;
                """)
                columns_info = cur.fetchall()
                columns = [col[0] for col in columns_info]
                types = {col[0]: col[1] for col in columns_info}
                
                cur.close()
                conn.close()
                
                response_data = {'columns': columns, 'types': types}
                return JsonResponse(response_data)
            except Exception as e:
                return JsonResponse({'error': str(e)}, status=500)

    # 1. Получаем список всех баз данных на сервере
    try:
        sys_conn = get_db_connection('postgres') 
        cur = sys_conn.cursor()
        cur.execute("SELECT datname FROM pg_database WHERE datistemplate = false;")
        databases = [row[0] for row in cur.fetchall()]
        cur.close()
        sys_conn.close()
    except Exception as e:
        error = f"Не удалось получить список баз: {str(e)}"
        databases = [default_db]

    # 2. Обработка действий пользователя (POST)
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'create_database':
            new_db_name = request.POST.get('new_db_name').strip()
            
            if not new_db_name:
                error = "Введите имя новой базы данных"
            elif new_db_name in databases:
                error = f"База '{new_db_name}' уже существует!"
            else:
                try:
                    sys_conn = get_db_connection('postgres')
                    sys_conn.autocommit = True
                    cur = sys_conn.cursor()
                    
                    if not new_db_name.replace('_', '').isalnum():
                        error = "Имя базы может содержать только буквы, цифры и подчеркивания."
                    else:
                        cur.execute(f"CREATE DATABASE \"{new_db_name}\"")
                        result_msg = {'type': 'success', 'message': f"База данных '{new_db_name}' успешно создана!"}
                        
                        cur.execute("SELECT datname FROM pg_database WHERE datistemplate = false;")
                        databases = [row[0] for row in cur.fetchall()]
                    
                    cur.close()
                    sys_conn.close()
                except Exception as e:
                    error = str(e)

        elif action == 'switch_db':
            new_db = request.POST.get('selected_db')
            if new_db and new_db in databases:
                return HttpResponseRedirect(f"?db={new_db}")
            else:
                error = "База данных не найдена."

        elif action == 'run_sql':
            query = request.POST.get('sql_query', '').strip()
            target_db = request.POST.get('target_db') or current_db_name
            
            if not query:
                error = "Введите SQL запрос"
            else:
                try:
                    conn = get_db_connection(target_db)
                    conn.autocommit = True
                    cur = conn.cursor()
                    
                    if query.upper().startswith(('DROP DATABASE',)):
                         error = "Запрещено удалять базы данных через консоль!"
                    else:
                        if query.strip().upper().startswith('SELECT'):
                            cur.execute(query)
                            columns = [desc[0] for desc in cur.description]
                            rows = cur.fetchall()
                            result_msg = {'type': 'select', 'columns': columns, 'rows': rows}
                        else:
                            cur.execute(query)
                            result_msg = {'type': 'success', 'message': f'Запрос выполнен в базе {target_db}. Затронуто строк: {cur.rowcount}'}
                        
                    cur.close()
                    conn.close()
                except Exception as e:
                    error = str(e)

        elif action == 'create_table_ui':
            table_name = request.POST.get('table_name')
            cols = request.POST.getlist('col_name')
            types = request.POST.getlist('col_type')
            target_db = request.POST.get('target_db') or current_db_name
            
            if table_name and cols:
                try:
                    conn = get_db_connection(target_db)
                    cur = conn.cursor()
                    col_defs = []
                    for i in range(len(cols)):
                        if cols[i].strip():
                            col_defs.append(f"{cols[i]} {types[i]}")
                    
                    if col_defs:
                        create_query = f"CREATE TABLE {table_name} ({', '.join(col_defs)})"
                        cur.execute(create_query)
                        conn.commit()
                        result_msg = {'type': 'success', 'message': f"Таблица '{table_name}' создана в базе {target_db}!"}
                    
                    conn.close()
                except Exception as e:
                    error = str(e)
            else:
                error = "Укажите имя таблицы и хотя бы одну колонку."

        elif action == 'delete_table':
            table_name = request.POST.get('table_name')
            target_db = request.POST.get('target_db') or current_db_name
            
            if not table_name:
                error = "Не указано имя таблицы для удаления"
            else:
                try:
                    conn = get_db_connection(target_db)
                    cur = conn.cursor()
                    cur.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
                    conn.commit()
                    result_msg = {'type': 'success', 'message': f"Таблица '{table_name}' успешно удалена!"}
                    
                    cur.execute("""
                        SELECT table_name 
                        FROM information_schema.tables 
                        WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
                    """)
                    all_tables = [row[0] for row in cur.fetchall()]
                    tables = [t for t in all_tables if t not in hidden_tables]
                    
                    if selected_table_name == table_name:
                        selected_table_data = None
                        selected_table_name = None
                        
                    cur.close()
                    conn.close()
                except Exception as e:
                    error = f"Ошибка при удалении таблицы: {str(e)}"

        elif action == 'insert_record':
            table_name = request.POST.get('table_name')
            target_db = request.POST.get('target_db') or current_db_name
            
            values = []
            keys = []
            for key, value in request.POST.items():
                if key.startswith('field_'):
                    keys.append(key.replace('field_', ''))
                    values.append(value)
            
            if table_name and keys:
                try:
                    conn = get_db_connection(target_db)
                    cur = conn.cursor()
                    placeholders = ', '.join(['%s'] * len(values))
                    query = f"INSERT INTO {table_name} ({', '.join(keys)}) VALUES ({placeholders})"
                    cur.execute(query, values)
                    conn.commit()
                    result_msg = {'type': 'success', 'message': 'Запись добавлена!'}
                    
                    cur.execute(f"SELECT * FROM {table_name}")
                    rows = cur.fetchall()
                    col_names = [desc[0] for desc in cur.description]
                    
                    cur.execute(f"""
                        SELECT column_name, data_type 
                        FROM information_schema.columns 
                        WHERE table_name = '{table_name}'
                        ORDER BY ordinal_position;
                    """)
                    columns_info = cur.fetchall()
                    types_dict = {col[0]: col[1] for col in columns_info}

                    selected_table_data = {
                        'columns': col_names, 
                        'rows': rows,
                        'types': types_dict
                    }
                    selected_table_name = table_name
                    
                    conn.close()
                except Exception as e:
                    error = str(e)

        elif action == 'delete_record':
            table_name = request.POST.get('table_name')
            pk_value = request.POST.get('pk_value')
            target_db = request.POST.get('target_db') or current_db_name
            
            if table_name and pk_value:
                try:
                    conn = get_db_connection(target_db)
                    cur = conn.cursor()
                    cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name='{table_name}' LIMIT 1")
                    pk_col_row = cur.fetchone()
                    
                    if pk_col_row:
                        pk_col = pk_col_row[0]
                        cur.execute(f"DELETE FROM {table_name} WHERE {pk_col} = %s", (pk_value,))
                        conn.commit()
                        result_msg = {'type': 'success', 'message': 'Запись удалена!'}
                        
                        cur.execute(f"SELECT * FROM {table_name}")
                        rows = cur.fetchall()
                        col_names = [desc[0] for desc in cur.description]
                        
                        cur.execute(f"""
                            SELECT column_name, data_type 
                            FROM information_schema.columns 
                            WHERE table_name = '{table_name}'
                            ORDER BY ordinal_position;
                        """)
                        columns_info = cur.fetchall()
                        types_dict = {col[0]: col[1] for col in columns_info}

                        selected_table_data = {
                            'columns': col_names, 
                            'rows': rows,
                            'types': types_dict
                        }
                        selected_table_name = table_name
                    else:
                        error = "Не удалось определить первичный ключ таблицы."
                    
                    conn.close()
                except Exception as e:
                    error = str(e)

    # 3. Получаем список таблиц для ТЕКУЩЕЙ ВЫБРАННОЙ БАЗЫ
    try:
        conn = get_db_connection(current_db_name)
        cur = conn.cursor()
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
        """)
        all_tables = [row[0] for row in cur.fetchall()]
        tables = [t for t in all_tables if t not in hidden_tables]
        cur.close()
        conn.close()
    except Exception as e:
        error = f"Ошибка получения списка таблиц: {str(e)}"

    # 4. Если выбрана конкретная таблица (?table=...), показываем её данные
    selected_table_name = request.GET.get('table')
    
    if selected_table_name and selected_table_name in tables and not selected_table_data:
        try:
            conn = get_db_connection(current_db_name)
            cur = conn.cursor()
            cur.execute(f"SELECT * FROM {selected_table_name}")
            
            columns = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
            
            cur.execute(f"""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = '{selected_table_name}'
                ORDER BY ordinal_position;
            """)
            columns_info = cur.fetchall()
            types_dict = {col[0]: col[1] for col in columns_info}
            
            selected_table_data = {
                'columns': columns,
                'rows': rows,
                'types': types_dict
            }
            
            cur.close()
            conn.close()
        except Exception as e:
            error = f"Ошибка чтения таблицы: {str(e)}"

    context = {
        'databases': databases,
        'tables': tables,
        'current_db_name': current_db_name,
        'result_msg': result_msg,
        'error': error,
        'selected_table_name': selected_table_name,
        'selected_table_data': selected_table_data
    }
    
    return render(request, 'cycle_app/main.html', context)