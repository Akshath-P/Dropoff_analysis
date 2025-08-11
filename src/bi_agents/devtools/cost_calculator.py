# model price per million tokens in dollars
model_prices = {
    "gpt-4o-mini": {'input_cost': 0.15, 'cached_input_cost': 0.075, 'output_cost': 0.60},
    "gpt-4o": {'input_cost': 2.5, 'cached_input_cost': 1.25, 'output_cost': 10.00},
    "gpt-4.1-mini": {'input_cost': 0.4, 'cached_input_cost': 0.1, 'output_cost': 1.60},
    "gpt-4.1-nano": {'input_cost': 0.1, 'cached_input_cost': 0.025, 'output_cost': 0.40},
    "gpt-4.1": {'input_cost': 2.00, 'cached_input_cost': 0.5, 'output_cost': 8.00}

}
def calculate_cost(prompt_tokens: int, completion_tokens: int, model_name : str):
    if model_name not in model_prices:
        return {'input_cost': 0.0, 'output_cost': 0.0, 'total_cost': 0.0}
    model = model_prices[model_name]
    input_cost = (prompt_tokens/1000000)*model['input_cost']
    output_cost = (completion_tokens/1000000)*model['output_cost']
    Results = {'input_cost': input_cost, 'output_cost':output_cost, 'total_cost': input_cost + output_cost}
    return Results
