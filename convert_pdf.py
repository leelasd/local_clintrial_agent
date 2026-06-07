from markitdown import MarkItDown
md = MarkItDown()
result = md.convert("/Users/leeladodda/Codes/clinical/Fundamentals_of_Clinical_Trials_4th_edition.pdf")
with open("/Users/leeladodda/Codes/clinical/Fundamentals_of_Clinical_Trials.md", "w") as f:
    f.write(result.text_content)
