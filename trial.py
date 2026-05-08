from presidio_analyzer import AnalyzerEngine

# Set up the engine, loads the NLP module (spaCy model by default) and other PII recognizers
analyzer = AnalyzerEngine()

# Call analyzer to get results
results = analyzer.analyze(text="My phone number is pvrithvik@gmail.com",
                           entities=["EMAIL_ADDRESS"],
                           language='en')
print(results)