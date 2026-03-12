import asyncio
from linkedin_bot.browser import create_browser_session

async def test_stealth() -> None:
    print("Iniciando prueba de Chromium Stealth...")
    async with create_browser_session() as session:
        print("Sesión creada exitosamente.")
        # Verificamos si podemos navegar a algo trivial o si CDP crashea
        await session.page.goto("https://bot.sannysoft.com/")
        print("Página antibot listada. Verifica consola.")
        # Pausa real para ver qué dice el sitio
        await asyncio.sleep(5)
        
        # Test 2: Inyectar código JS para ver el valor de webdriver nativo
        wd_status = await session.page.evaluate("navigator.webdriver")
        print(f"Estado de navigator.webdriver detectado: {wd_status} (Debe ser False y natural)")
        
        print("Cerrando exitosamente.")

if __name__ == "__main__":
    asyncio.run(test_stealth())
