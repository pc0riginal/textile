"""Utility functions for the application"""

def number_to_words(number):
    """Convert a number to words (Indian numbering system)"""
    
    if number == 0:
        return "ZERO ONLY"
    
    # Handle decimal part
    if isinstance(number, float):
        number = int(round(number))
    
    ones = ["", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE"]
    tens = ["", "", "TWENTY", "THIRTY", "FORTY", "FIFTY", "SIXTY", "SEVENTY", "EIGHTY", "NINETY"]
    teens = ["TEN", "ELEVEN", "TWELVE", "THIRTEEN", "FOURTEEN", "FIFTEEN", "SIXTEEN", "SEVENTEEN", "EIGHTEEN", "NINETEEN"]
    
    def convert_below_thousand(n):
        if n == 0:
            return ""
        elif n < 10:
            return ones[n]
        elif n < 20:
            return teens[n - 10]
        elif n < 100:
            return tens[n // 10] + (" " + ones[n % 10] if n % 10 != 0 else "")
        else:
            return ones[n // 100] + " HUNDRED" + (" " + convert_below_thousand(n % 100) if n % 100 != 0 else "")
    
    if number < 0:
        return "MINUS " + number_to_words(abs(number))
    
    if number < 1000:
        result = convert_below_thousand(number)
    elif number < 100000:  # Less than 1 lakh
        thousands = number // 1000
        remainder = number % 1000
        result = convert_below_thousand(thousands) + " THOUSAND"
        if remainder > 0:
            result += " " + convert_below_thousand(remainder)
    elif number < 10000000:  # Less than 1 crore
        lakhs = number // 100000
        remainder = number % 100000
        result = convert_below_thousand(lakhs) + " LAKH"
        if remainder >= 1000:
            result += " " + convert_below_thousand(remainder // 1000) + " THOUSAND"
            remainder = remainder % 1000
        if remainder > 0:
            result += " " + convert_below_thousand(remainder)
    else:  # Crores
        crores = number // 10000000
        remainder = number % 10000000
        result = convert_below_thousand(crores) + " CRORE"
        if remainder >= 100000:
            result += " " + convert_below_thousand(remainder // 100000) + " LAKH"
            remainder = remainder % 100000
        if remainder >= 1000:
            result += " " + convert_below_thousand(remainder // 1000) + " THOUSAND"
            remainder = remainder % 1000
        if remainder > 0:
            result += " " + convert_below_thousand(remainder)
    
    return result.strip() + " ONLY"
