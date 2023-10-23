import re

my_string = "Hello {{name}}, your age is {{age}} years old."
my_dict = {"name": "John", "age": 30}

# Define a regular expression pattern to match substrings enclosed within double curly braces
pattern = r"\{\{(\w+)\}\}"

# Replace substrings enclosed within double curly braces with values from a dictionary using regex
modified_string = re.sub(pattern, lambda match: str(my_dict.get(match.group(1))), my_string)

print(modified_string)