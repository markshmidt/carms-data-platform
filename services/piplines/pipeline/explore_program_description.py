import json

with open("../../../data/raw/1503_markdown_program_descriptions.json") as f:
    data = json.load(f)

print(type(data)) # list
print(len(data)) #815 programs
print(data[0].keys()) # ['page_content', 'metadata']
print(data[0]['page_content']) # markdown text
print(data[0]['metadata']) # metadata with source


with open("../../../data/raw/1503_program_descriptions_v2.json") as f:
    data_v2 = json.load(f)
print(type(data_v2)) # list
print(len(data_v2)) #815 programs
print(data_v2[0].keys()) # ['id',page_content', 'metadata']
# print(data_v2[0]['page_content']) #html+js
# print(data_v2[0]['metadata']) # source url
print(data_v2[0]['id']) # program id like 1503|27447


with open("../../../data/raw/1503_markdown_program_descriptions_v2.json") as f:
    data_v3 = json.load(f)
print(type(data_v3)) # list
print(len(data_v3)) #815 programs
print(data_v3[0].keys()) # ['id',page_content', 'metadata']
print(data_v3[0]['page_content']) #markdown text
print(data_v3[0]['metadata']) # source url
print(data_v3[0]['id']) # program id like 1503|27447

