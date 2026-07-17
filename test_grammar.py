from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

MODEL = "vennify/t5-base-grammar-correction"

tokenizer = AutoTokenizer.from_pretrained(MODEL)
model = AutoModelForSeq2SeqLM.from_pretrained(MODEL)

sentence = "He go to school every day."

inputs = tokenizer(
    sentence,
    return_tensors="pt",
)

outputs = model.generate(
    **inputs,
    max_new_tokens=64,
)

print(
    tokenizer.decode(
        outputs[0],
        skip_special_tokens=True,
    )
)