import pandas as pd

# Load the excel file to check its structure
file_path = "SOLIEUDO_TONGHOP.xlsx"
try:
    xls = pd.ExcelFile(file_path)
    sheet_names = xls.sheet_names
    print(f"Sheets: {sheet_names}")
    
    # Read the first sheet
    df = pd.read_excel(file_path, sheet_name=sheet_names[0])
    print(df.head())
    print("Columns:", df.columns.tolist())
except Exception as e:
    print(f"Error: {e}")