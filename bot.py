import discord
from discord import app_commands
import aiohttp
import os
import random
import asyncio
import json
from dotenv import load_dotenv
import logging

# Configurar o logging para capturar erros e informações
logging.basicConfig(level=logging.INFO)

# Carregar variáveis do arquivo .env
load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
RIOT_API_KEY = os.getenv('RIOT_API_KEY')

# Funções para carregar e salvar contas registradas
def load_registered_accounts():
    try:
        with open('registered_accounts.json', 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return {}

def save_registered_accounts(accounts):
    with open('registered_accounts.json', 'w') as file:
        json.dump(accounts, file)

# Funções para carregar e salvar o canal de notificações
def load_notification_channel():
    try:
        with open('notification_channel.json', 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return None

def save_notification_channel(channel_id):
    with open('notification_channel.json', 'w') as file:
        json.dump(channel_id, file)

# Inicialização
registered_accounts = load_registered_accounts()
notification_channel_id = load_notification_channel()

# Cache para resultados de partidas recentes (armazenando múltiplas partidas para evitar repetições)
match_cache = {}

class MyClient(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.messages = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()

client = MyClient()

# Função para obter informações da conta com base no Riot ID e Tagline
async def get_account_info(riot_id, tagline):
    async with aiohttp.ClientSession() as session:
        try:
            url = f"https://americas.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{riot_id}/{tagline}?api_key={RIOT_API_KEY}"
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 404:
                    logging.error("Conta não encontrada.")
                    return None
                else:
                    logging.error(f"Erro ao buscar conta: {response.status}, {await response.text()}")
        except Exception as e:
            logging.error(f"Erro durante a chamada à API Riot: {e}")
    return None

# Função para obter as últimas 2 partidas do jogador
async def get_recent_matches(puuid):
    async with aiohttp.ClientSession() as session:
        try:
            url = f"https://americas.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?start=0&count=2&api_key={RIOT_API_KEY}"
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logging.error(f"Erro ao buscar partidas: {response.status}, {await response.text()}")
        except Exception as e:
            logging.error(f"Erro durante a chamada à API Riot: {e}")
    return None

# Função para obter os detalhes de uma partida
async def get_match_details(match_id):
    async with aiohttp.ClientSession() as session:
        try:
            url = f"https://americas.api.riotgames.com/lol/match/v5/matches/{match_id}?api_key={RIOT_API_KEY}"
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logging.error(f"Erro ao buscar detalhes da partida {match_id}: {response.status}, {await response.text()}")
        except Exception as e:
            logging.error(f"Erro durante a chamada à API Riot: {e}")
    return None

# Função para extrair informações relevantes da partida
async def extract_match_info(match_data, puuid):
    participants = match_data['info']['participants']
    player_data = next((player for player in participants if player['puuid'] == puuid), None)

    if player_data:
        champion_name = player_data['championName']
        invoker_name = player_data['summonerName']
        win_status = "💅 ACHEI FÁCIL" if player_data['win'] else "🤡 KKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKK"
        game_mode = match_data['info']['gameMode']

        # Obter a versão atual do Data Dragon
        async with aiohttp.ClientSession() as session:
            dd_version_url = "https://ddragon.leagueoflegends.com/api/versions.json"
            async with session.get(dd_version_url) as dd_version_response:
                if dd_version_response.status == 200:
                    latest_version = (await dd_version_response.json())[0]
                else:
                    latest_version = "12.10.1"  # Fallback para uma versão específica

        champion_image_url = f"http://ddragon.leagueoflegends.com/cdn/{latest_version}/img/champion/{champion_name}.png"
        kills = player_data['kills']
        deaths = player_data['deaths']
        assists = player_data['assists']

        return {
            "champion": champion_name,
            "invoker": invoker_name,
            "status": win_status,
            "image_url": champion_image_url,
            "kda": f"{kills}/{deaths}/{assists}",
            "game_mode": game_mode,
            "win": player_data['win']
        }
    return None

# Cache para armazenar o último match ID enviado para cada jogador
last_match_ids = {}

# Função para monitorar as partidas de um jogador
async def monitor_player_matches(puuid):
    global notification_channel_id
    match_ids = await get_recent_matches(puuid)
    if match_ids:
        current_match_id = match_ids[0]

        # Verifica se o último ID de partida enviado é diferente do atual
        if last_match_ids.get(puuid) != current_match_id:
            last_match_ids[puuid] = current_match_id  # Atualiza o último ID de partida

            match_data = await get_match_details(current_match_id)
            if match_data:
                match_info = await extract_match_info(match_data, puuid)

                if match_info:
                    channel = client.get_channel(notification_channel_id)
                    if channel:
                        embed_color = discord.Color.blue() if match_info['win'] else discord.Color.red()
                        
                        # Define o título com base na vitória ou derrota
                        if match_info['win']:
                            title = f"{match_info['invoker']} amassou de {match_info['champion']}"
                        else:
                            title = f"{match_info['invoker']} se fudeu de {match_info['champion']}"

                        embed = discord.Embed(
                            title=title,
                            description="saiu do inferno (voltar em breve ass: demonio 👹)",
                            color=embed_color
                        )
                        embed.add_field(
                            name=f"Resultado: {match_info['status']}",
                            value=f"KDA: {match_info['kda']}\n{match_info['game_mode']} de cria",
                            inline=False
                        )
                        embed.set_image(url=match_info['image_url'])

                        await channel.send(embed=embed)

# Função para monitorar todas as contas registradas
async def monitor_all_matches():
    while True:
        tasks = [monitor_player_matches(puuid) for puuid in registered_accounts]
        await asyncio.gather(*tasks)
        await asyncio.sleep(60)  # Verifica a cada 1 minuto (ajustável conforme necessidade)

# Função para registrar um jogador
@client.tree.command(name="registrar", description="Registrar um jogador para monitoramento de partidas")
@app_commands.describe(riot_id="Riot ID do jogador", tagline="Tagline do jogador")
async def registrar(interaction: discord.Interaction, riot_id: str, tagline: str):
    await interaction.response.defer()  # Evitar timeout
    account_info = await get_account_info(riot_id, tagline)

    if account_info:
        puuid = account_info['puuid']
        if puuid in registered_accounts:
            await interaction.followup.send(f"A conta já está registrada.")
            return
        
        registered_accounts[puuid] = str(interaction.user.id)
        save_registered_accounts(registered_accounts)

        embed = discord.Embed(
            title="Jogador Registrado!",
            description=f"{interaction.user.mention} registrou a conta com sucesso!",
            color=discord.Color.green()
        )
        embed.add_field(name="Riot ID", value=riot_id, inline=True)
        embed.add_field(name="Tagline", value=tagline, inline=True)
        
        await interaction.followup.send(embed=embed)

        # Inicia o monitoramento
        await monitor_all_matches()
    else:
        await interaction.followup.send("Não foi possível encontrar a conta especificada. Verifique o Riot ID e o Tagline.")

# Comando para definir o canal de notificações (somente administradores)
@client.tree.command(name="set_channel", description="Definir o canal onde as notificações serão enviadas")
@commands.has_permissions(administrator=True)  # Apenas administradores podem usar
async def set_channel(interaction: discord.Interaction):
    global notification_channel_id
    notification_channel_id = interaction.channel.id
    save_notification_channel(notification_channel_id)
    await interaction.response.send_message(f"Canal de notificações configurado para {interaction.channel.mention}")

# Tratamento de erro para comandos de permissão
@set_channel.error
async def set_channel_error(interaction: discord.Interaction, error):
    if isinstance(error, commands.MissingPermissions):
        await interaction.response.send_message("Você não tem permissão para usar este comando.")

# Comando para fornecer um tutorial
@client.tree.command(name="tutorial", description="Explica como usar o comando /registrar")
async def tutorial(interaction: discord.Interaction):
    tutorial_message = (
        "**Como se registrar-se a si mesmo**\n\n"
        "Para se registrar, você deve usar o comando `/registrar` seguido do seu NOME DO LOL e da TAGLINE (SEM O HASHTAG - #).\n"
        "Exemplo: `/registrar NomeDoLol TagName`\n\n"
        "A fofoqueira irá buscar as informações da conta e, se encontrada, irá registrá-la para monitoramento de partidas.\n"
        "Após o registro, a fofoqueira começará a monitorar as partidas desse jogador.\n"
        "Se você tiver mais alguma dúvida, sinta-se à vontade para perguntar!\n"
        "Sugestoes apenas por 10 reais no pix"
    )
    await interaction.response.send_message(tutorial_message)

# Função principal
async def main():
    try:
        async with client:
            await client.start(DISCORD_TOKEN)
    except asyncio.CancelledError:
        logging.warning("O loop de eventos foi cancelado.")
    finally:
        logging.info("Desconectando o bot...")
        await client.close()

# Iniciar o bot
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot foi interrompido pelo usuário.")