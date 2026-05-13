import glob
import re
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import DoubleQuotedScalarString

def to_snake_case(name):
    """Converts camelCase or PascalCase to snake_case."""
    s1 = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', name)
    s2 = re.sub(r'([a-z\d])([A-Z])', r'\1_\2', s1)
    return s2.lower()

def format_cube_models():
    yaml = YAML()
    yaml.preserve_quotes = True 
    yaml.indent(mapping=2, sequence=4, offset=2)

    files = glob.glob('model/cubes/**/*.yml', recursive=True)
    if not files:
        print("No YAML files found.")
        return

    for filepath in files:
        modified = False
        
        with open(filepath, 'r', encoding='utf-8') as f:
            try:
                data = yaml.load(f)
            except Exception as e:
                print(f"Failed to parse {filepath}: {e}")
                continue

        if not data or 'cubes' not in data:
            continue

        for cube in data['cubes']:
            cube_name = cube.get('name', '')
            dimension_lookup = {}
            valid_fields = set() 

            # ==========================================
            # PASS 1: Format Dimensions & Measures
            # ==========================================
            for block in ['dimensions', 'measures']:
                if block in cube:
                    for item in cube[block]:
                        sql_val = item.get('sql')
                        true_col_name = None

                        # 1. Standardize SQL format
                        if isinstance(sql_val, str):
                            if re.match(r'^[a-zA-Z0-9_]+$', sql_val):
                                item['sql'] = DoubleQuotedScalarString(f"{{CUBE}}.`{sql_val}`")
                                true_col_name = sql_val
                                modified = True
                            else:
                                # FIXED: Added ^ and $ anchors so it only extracts if it's a single column
                                match = re.match(r'^\{CUBE\}\.?\`?([a-zA-Z0-9_]+)\`?$', sql_val.strip())
                                if match:
                                    true_col_name = match.group(1)

                        if not true_col_name:
                            true_col_name = item.get('name', '')

                        # 2. Standardize Name format to snake_case
                        if true_col_name and re.match(r'^[a-zA-Z0-9_]+$', true_col_name):
                            snake_name = to_snake_case(true_col_name)
                            if item.get('name') != snake_name:
                                item['name'] = snake_name
                                modified = True
                            
                            # 3. Add to our lookup dictionary for Pass 2
                            fuzzy_key = true_col_name.replace('_', '').lower()
                            dimension_lookup[fuzzy_key] = snake_name
                        
                        # Track every final dimension/measure name for Pass 3
                        final_name = item.get('name')
                        if final_name:
                            valid_fields.add(final_name)

            # ==========================================
            # PASS 2: Format Joins using the Lookup Dict
            # ==========================================
            if 'joins' in cube:
                for join in cube['joins']:
                    join_sql = join.get('sql')
                    if isinstance(join_sql, str):
                        
                        def replace_join_ref(match):
                            prefix = match.group(1)
                            dim_ref = match.group(2)
                            
                            if prefix == 'CUBE' or prefix == cube_name:
                                fuzzy_dim = dim_ref.replace('_', '').lower()
                                if fuzzy_dim in dimension_lookup:
                                    return f"{{{prefix}.{dimension_lookup[fuzzy_dim]}}}"
                            return match.group(0)

                        new_sql = re.sub(r'\{([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)\}', replace_join_ref, join_sql)
                        
                        if join_sql != new_sql:
                            join['sql'] = DoubleQuotedScalarString(new_sql)
                            modified = True

            # ==========================================
            # PASS 3: Format Complex SQL Math Expressions
            # ==========================================
            for block in ['dimensions', 'measures']:
                if block in cube:
                    for item in cube[block]:
                        sql_val = item.get('sql')
                        if isinstance(sql_val, str):
                            
                            def replace_math_ref(match):
                                word = match.group(1)
                                start = match.start()
                                
                                if start > 0 and match.string[start - 1] in ['.', '{', '`', '}']:
                                    return word
                                    
                                if word in valid_fields and word != 'CUBE':
                                    return f"{{CUBE}}.{word}"
                                
                                return word

                            new_sql = re.sub(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b', replace_math_ref, sql_val)
                            
                            if sql_val != new_sql:
                                item['sql'] = DoubleQuotedScalarString(new_sql)
                                modified = True

        if modified:
            with open(filepath, 'w', encoding='utf-8') as f:
                yaml.dump(data, f)
            print(f"Updated: {filepath}")

    print("Done formatting cubes!")

if __name__ == "__main__":
    format_cube_models()