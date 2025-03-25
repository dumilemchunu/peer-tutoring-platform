import re

# Read the original file
with open('app/services/firebase_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the problematic get_module_by_code method with a corrected version
pattern = r'def get_module_by_code\(self, module_code\):.*?(?=def|$)'
replacement = '''def get_module_by_code(self, module_code):
    """
    Get a module by its code (alias for get_module for backwards compatibility)
    """
    return self.get_module(module_code)

'''

# Use DOTALL flag to match across newlines
fixed_content = re.sub(pattern, replacement, content, flags=re.DOTALL)

# Write the fixed content back to the file
with open('app/services/firebase_service.py', 'w', encoding='utf-8') as f:
    f.write(fixed_content)

print("Fixed firebase_service.py file successfully!") 