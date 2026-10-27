from typing import Any
import asyncio
import httpx
import os
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
port = int(os.getenv("PORT", 8085))
mcp = FastMCP("weather", host="0.0.0.0", port=port)

# Constants
WEATHERAPI_BASE = "https://api.weatherapi.com/v1"
USER_AGENT = "weather-app/1.0"

# Get API key from environment variable
API_KEY = os.getenv("WEATHERAPI_KEY")

# Chế độ mock: trả dữ liệu giả cùng schema với WeatherAPI, dùng để demo/test khi
# không có API key. Bật bằng WEATHER_MOCK=1. Kết quả luôn được gắn nhãn [MOCK DATA].
MOCK = os.getenv("WEATHER_MOCK", "").lower() in ("1", "true", "yes")
MOCK_TAG = "[MOCK DATA - not real weather]"

def mock_weather_response(endpoint: str, params: dict[str, str]) -> dict[str, Any]:
    """Build a fake response with the same shape as WeatherAPI.com."""
    city = params["q"]
    # Nhiệt độ giả nhưng ổn định theo tên thành phố (cùng city -> cùng kết quả)
    base = 20 + sum(map(ord, city.lower())) % 15
    location = {"name": city.title(), "region": "Mock Region", "country": "Mockland"}
    if endpoint == "current.json":
        return {
            "location": location,
            "current": {
                "temp_c": float(base), "temp_f": round(base * 9 / 5 + 32, 1),
                "feelslike_c": float(base + 1), "feelslike_f": round((base + 1) * 9 / 5 + 32, 1),
                "condition": {"text": "Partly cloudy"},
                "humidity": 70, "wind_kph": 12.0, "wind_mph": 7.5, "wind_dir": "NE",
                "pressure_mb": 1012.0, "uv": 6.0, "vis_km": 10.0,
                "last_updated": "2026-01-01 12:00",
            },
        }
    days = int(params["days"])
    return {
        "location": location,
        "forecast": {"forecastday": [
            {
                "date": f"2026-01-{i + 1:02d}",
                "day": {
                    "maxtemp_c": float(base + i), "maxtemp_f": round((base + i) * 9 / 5 + 32, 1),
                    "mintemp_c": float(base - 6 + i), "mintemp_f": round((base - 6 + i) * 9 / 5 + 32, 1),
                    "condition": {"text": ["Sunny", "Light rain", "Cloudy"][i % 3]},
                    "daily_chance_of_rain": 10 + 20 * i, "maxwind_kph": 15.0 + i, "uv": 7.0,
                },
            }
            for i in range(days)
        ]},
    }

async def make_weather_request(endpoint: str, params: dict[str, str]) -> dict[str, Any] | None:
    """Make a request to the WeatherAPI with proper error handling."""
    if MOCK:
        return mock_weather_response(endpoint, params)

    # Check if API key is set
    if not API_KEY:
        print("ERROR: WeatherAPI key not set. Please set WEATHERAPI_KEY environment variable.")
        return None
        
    headers = {
        "User-Agent": USER_AGENT,
    }
    # Add API key to parameters
    params["key"] = API_KEY
    
    url = f"{WEATHERAPI_BASE}/{endpoint}"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, params=params, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            print(f"HTTP Error {e.response.status_code}: {e.response.text}")
            return None
        except httpx.RequestError as e:
            print(f"Request Error: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error: {e}")
            return None

@mcp.tool()
async def get_current_weather(city: str) -> str:
    """Get current weather conditions for a city.

    Args:
        city: City name (e.g., "Hanoi", "Haiphong", "Danang", "Brisbane", "Sydney")
    """
    params = {
        "q": city,
        "aqi": "no"
    }
    
    data = await make_weather_request("current.json", params)

    if not data:
        if not API_KEY:
            return f"❌ WeatherAPI key not configured. Please set WEATHERAPI_KEY environment variable with your API key from weatherapi.com"
        return f"Unable to fetch current weather data for {city}. Please check the city name and API key configuration."

    current = data["current"]
    location = data["location"]
    
    return f"""{MOCK_TAG if MOCK else ""}
Current Weather for {location['name']}, {location['region']}, {location['country']}:

Temperature: {current['temp_c']}°C ({current['temp_f']}°F)
Feels like: {current['feelslike_c']}°C ({current['feelslike_f']}°F)
Condition: {current['condition']['text']}
Humidity: {current['humidity']}%
Wind: {current['wind_kph']} km/h ({current['wind_mph']} mph) {current['wind_dir']}
Pressure: {current['pressure_mb']} mb
UV Index: {current['uv']}
Visibility: {current['vis_km']} km

Last updated: {current['last_updated']}
"""

@mcp.tool()
async def get_forecast(city: str, days: int = 3) -> str:
    """Get weather forecast for a city.

    Args:
        city: City name (e.g., "Hanoi", "Haiphong", "Danang", "Brisbane", "Sydney", "Melbourne")
        days: Number of days to forecast (1-3 for free tier, max 10 for paid)
    """
    # Limit days to 3 for free tier
    days = min(days, 3)
    
    params = {
        "q": city,
        "days": str(days),
        "aqi": "no",
        "alerts": "no"
    }
    
    data = await make_weather_request("forecast.json", params)

    if not data:
        if not API_KEY:
            return f"❌ WeatherAPI key not configured. Please set WEATHERAPI_KEY environment variable with your API key from weatherapi.com"
        return f"Unable to fetch forecast data for {city}. Please check the city name and API key configuration."

    location = data["location"]
    forecast_days = data["forecast"]["forecastday"]
    
    forecasts = []
    if MOCK:
        forecasts.append(MOCK_TAG)
    forecasts.append(f"Weather Forecast for {location['name']}, {location['region']}, {location['country']}:")
    
    for day in forecast_days:
        day_data = day["day"]
        date = day["date"]
        
        forecast = f"""
{date}:
High: {day_data['maxtemp_c']}°C ({day_data['maxtemp_f']}°F)
Low: {day_data['mintemp_c']}°C ({day_data['mintemp_f']}°F)
Condition: {day_data['condition']['text']}
Chance of Rain: {day_data['daily_chance_of_rain']}%
Max Wind: {day_data['maxwind_kph']} km/h
UV Index: {day_data['uv']}
"""
        forecasts.append(forecast)

    return "\n---\n".join(forecasts)

@mcp.tool()
async def health_check() -> str:
    """Health check endpoint for deployment verification."""
    mode = " (MOCK mode)" if MOCK else ""
    return f"✅ Weather MCP Server is running{mode}! Ready to provide weather data for Australian cities and worldwide."

print("✅ MCP server initialized with Streamable HTTP transport")
print("🔧 Available tools: get_current_weather, get_forecast, health_check")

if __name__ == "__main__":
    import sys
    
    is_cloud_run = bool(os.getenv("PORT"))
    is_standalone = len(sys.argv) == 1 and sys.stdin.isatty()
    
    if is_cloud_run or is_standalone:
        print(f"🚀 Starting MCP server on http://0.0.0.0:{port}/mcp")
        mcp.run(transport="streamable-http")
    else:
        print("Starting FastMCP server in stdio mode for local client", file=sys.stderr)
        mcp.run()