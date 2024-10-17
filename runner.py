from telethon import TelegramClient, events, types
import requests, asyncio, logging, requests_toolbelt, os, secrets, mimetypes, dotenv
dotenv.load_dotenv()
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO, encoding='utf-8')
logger = logging.getLogger(__name__)
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

transcription_modes = {}

client = TelegramClient('orion_bot', API_ID, API_HASH)

@client.on(events.NewMessage(pattern='/start'))
async def start(event):
    """Envía un mensaje de bienvenida al usuario."""
    await event.respond("¡Hola! Soy Orion IA Bot. ¿En qué puedo ayudarte?")

@client.on(events.NewMessage(pattern='/toggle_transcription'))
async def toggle_transcription(event):
    """Toggle audio transcription mode."""
    user_id = str(event.message.sender_id)
    transcription_modes[user_id] = not transcription_modes.get(user_id, False)
    await event.respond(f"Transcription mode is now {'on' if transcription_modes[user_id] else 'off'}.")

@client.on(events.NewMessage(pattern='/attach_link'))
async def attach_link(event):
    await event.respond("Not implemented yet!")

@client.on(events.NewMessage(incoming=True)) 
async def handle_message(event: events.NewMessage.Event):
    """Maneja diferentes tipos de mensajes."""
    if event.message.message and any(map(lambda word: word in event.message.message.lower(), ['/start', '/toggle_transcription', '/attach_link'])):
        return
    try:
        if any(map(lambda type: isinstance(event.media, type), [types.MessageMediaPhoto, types.MessageMediaDocument])):
            await send_content(event)

        elif event.media is None and event.message.message:
            await talk(event)

        else:
            await event.respond("Aún no puedo manejar este tipo de contenido, ¡pero dame tiempo!")

    except requests.exceptions.RequestException as e:
        logging.error(f"Error al comunicar con la API: {e}")
        await event.respond("Lo siento, hubo un error al procesar tu solicitud. Por favor, inténtalo de nuevo más tarde.")

async def handle_file(event, name:str, list_of_files: list):
    file_path: str = await client.download_media(event.message, f"data/{name}") # type: ignore
    content_type, _ = mimetypes.guess_type(file_path)
    if not content_type:
        content_type = 'application/octet-stream'
    list_of_files.append(('files', (name, open(file_path, 'rb'), content_type)))

async def send_content(event: events.NewMessage.Event):
    """Sends content (files) to the API."""
    user_id = str(event.message.sender_id)
    files = []

    if event.message.media:
        for document in event.message.media.document.attributes:
            try:
                if isinstance(document, types.DocumentAttributeFilename):
                    file_name = document.file_name
                elif isinstance(document, types.DocumentAttributeAudio):
                    file_name = f"{secrets.token_hex(8)}.ogg"
                    event.message.message = "User sent an audio file. Your purpose is to reply to him."

                await handle_file(event, file_name, files)
            except Exception as e:
                logging.error(f"Error downloading media: {e}")
                await event.respond("Sorry, there was an error downloading the file.")

    params = {
        'text': event.message.message,
        'user_id': user_id
    }

    try:
        mp_encoder = requests_toolbelt.MultipartEncoder(fields={file[0]: (file[1][0], file[1][1], file[1][2]) for file in files})
        if transcription_modes.get(user_id, False) and any(file[1][2].startswith('audio') for file in files):
            logger.info('Transcribing audio file...')
            response = await transcribe(mp_encoder)
        else:
            response = await talk_content(params, mp_encoder)
        response.raise_for_status()
        logger.info(response.content)
        await event.respond(response.text)
        return
    except requests.exceptions.RequestException as e:
        logging.error(f"API Error: {e}")
        await event.respond("Sorry, there was an error processing your request.")
    finally:
        for file in files:
            file[1][1].close()

async def talk_content(params, mp_encoder):
    url = f"{API_BASE_URL}" + '/talk/content'
    return requests.post(url, params=params, data=mp_encoder, headers={'Content-Type': mp_encoder.content_type})

async def transcribe(mp_encoder):
    url = f"{API_BASE_URL}" + '/transcribe'
    return requests.post(url, data=mp_encoder, headers={'Content-Type': mp_encoder.content_type})

async def talk(event: events.NewMessage.Event):
    """Envía el mensaje del usuario a la API Orion y devuelve la respuesta."""
    text = event.message.message
    try:
        response = requests.post(f"{API_BASE_URL}/talk", params={"content": text, "user_id": event.message.sender_id})
        response.raise_for_status()
        await event.respond(response.text)
    except requests.exceptions.RequestException as e:
        logging.error(f"Error al comunicar con la API: {e}")
        await event.respond("Lo siento, hubo un error al procesar tu solicitud. Por favor, inténtalo de nuevo más tarde.")


async def main():
    """Inicia el bot."""
    await client.start(bot_token=BOT_TOKEN) # type: ignore
    await client.run_until_disconnected()   # type: ignore

if __name__ == '__main__':
    asyncio.run(main())