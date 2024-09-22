import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import os
import asyncio
import json
from dotenv import load_dotenv
import logging
from datetime import datetime, timedelta  # Para expiração de cache

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

# Cache para resultados de partidas recentes com expiração
match_cache = {}
cache_expiration_minutes = 10  # Expira em 10 minutos por padrão

# Cache para armazenar o último match ID enviado para cada jogador
last_match_ids = {}

# Intervalo configurável de monitoramento (em segundos)
monitoring_interval = 60  # Padrão: 60 segundos

class MyClient(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.messages = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()

client = MyClient()

# Função para obter informações da conta com base no Riot ID e Tagline, com retry
async def get_account_info(riot_id, tagline, retries=3):
    for attempt in range(retries):
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
        await asyncio.sleep(2)  # Espera 2 segundos antes de tentar novamente
    return None

# Função para obter as últimas 2 partidas do jogador, com retry
async def get_recent_matches(puuid, retries=3):
    for attempt in range(retries):
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
        await asyncio.sleep(2)  # Espera 2 segundos antes de tentar novamente
    return None

# Função para obter os detalhes de uma partida, com retry
async def get_match_details(match_id, retries=3):
    for attempt in range(retries):
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
        await asyncio.sleep(2)  # Espera 2 segundos antes de tentar novamente
    return None

# Função para extrair informações relevantes da partida
async def extract_match_info(match_data, puuid):
    participants = match_data['info']['participants']
    player_data = next((player for player in participants if player['puuid'] == puuid), None)

    if player_data:
        champion_name = player_data['championName']
        invoker_name = player_data['summonerName']
        win_status = "💅 ACHEI FÁCIL" if player_data['win'] else "🤡 KKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKK"
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

# Função para verificar se o cache expirou
def has_cache_expired(puuid, match_id):
    if puuid in match_cache:
        cache_entry = match_cache[puuid]
        if cache_entry['match_id'] == match_id and cache_entry['timestamp'] > datetime.now() - timedelta(minutes=cache_expiration_minutes):
            return False
    return True

# Função para monitorar as partidas de um jogador
async def monitor_player_matches(puuid):
    global notification_channel_id
    match_ids = await get_recent_matches(puuid)
    if match_ids:
        current_match_id = match_ids[0]

        # Verifica se o último ID de partida enviado é diferente do atual e se o cache expirou
        if last_match_ids.get(puuid) != current_match_id and has_cache_expired(puuid, current_match_id):
            last_match_ids[puuid] = current_match_id  # Atualiza o último ID de partida
            match_cache[puuid] = {"match_id": current_match_id, "timestamp": datetime.now()}  # Atualiza o cache

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
    global monitoring_interval
    while True:
        tasks = [monitor_player_matches(puuid) for puuid in registered_accounts]
        await asyncio.gather(*tasks)
        await asyncio.sleep(monitoring_interval)  # Intervalo configurável

# Comando para registrar um jogador
@client.tree.command(name="registrar", description="Registre um jogador para monitoramento de partidas.")
async def registrar(interaction: discord.Interaction, riot_id: str, tagline: str):
    account_info = await get_account_info(riot_id, tagline)
    if account_info:
        puuid = account_info['puuid']
        registered_accounts[puuid] = {
            'riot_id': riot_id,
            'tagline': tagline,
            'puuid': puuid
        }
        save_registered_accounts(registered_accounts)
        await interaction.response.send_message(f"Jogador {riot_id}#{tagline} registrado com sucesso!")
    else:
        await interaction.response.send_message(f"Não foi possível registrar o jogador {riot_id}#{tagline}. Verifique se o Riot ID e a tagline estão corretos.")

# Comando para definir o canal de notificação
@client.tree.command(name="set_channel", description="Defina o canal para enviar notificações de partidas.")
async def set_channel(interaction: discord.Interaction):
    global notification_channel_id
    notification_channel_id = interaction.channel.id
    save_notification_channel(notification_channel_id)
    await interaction.response.send_message(f"Canal definido para notificações: {interaction.channel.name}")

# Comando para definir o intervalo de monitoramento
@client.tree.command(name="set_interval", description="Defina o intervalo entre verificações de partidas (em segundos).")
async def set_interval(interaction: discord.Interaction, interval: int):
    global monitoring_interval
    if interval < 10:  # Define um valor mínimo de 10 segundos
        await interaction.response.send_message("O intervalo mínimo é de 10 segundos.")
    else:
        monitoring_interval = interval
        await interaction.response.send_message(f"Intervalo de monitoramento ajustado para {interval} segundos.")

from discord.ext import commands

# Comando para testar o envio do embed puxando a última partida de um jogador registrado
@client.tree.command(name="test_embed", description="Teste o envio de um embed com base na última partida de um jogador registrado.")
@commands.has_permissions(administrator=True)  # Verifica se o usuário é administrador
async def test_embed(interaction: discord.Interaction, riot_id: str, tagline: str):
    # Verificar se o jogador está registrado
    for puuid, account in registered_accounts.items():
        if account['riot_id'] == riot_id and account['tagline'] == tagline:
            # Buscar as últimas partidas do jogador
            match_ids = await get_recent_matches(puuid)
            if match_ids:
                # Pegar o ID da última partida
                last_match_id = match_ids[0]
                
                # Buscar detalhes da última partida
                match_data = await get_match_details(last_match_id)
                if match_data:
                    # Extrair informações da partida
                    match_info = await extract_match_info(match_data, puuid)
                    if match_info:
                        embed_color = discord.Color.blue() if match_info['win'] else discord.Color.red()
                        title = f"{match_info['invoker']} amassou de {match_info['champion']}" if match_info['win'] else f"{match_info['invoker']} se fudeu de {match_info['champion']}"

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

                        # Enviar o embed com as informações da última partida
                        await interaction.response.send_message(embed=embed)
                        return

            # Se não encontrar partidas recentes
            await interaction.response.send_message(f"Não foi possível encontrar partidas recentes para {riot_id}#{tagline}.")
            return

    # Se o jogador não estiver registrado
    await interaction.response.send_message(f"O jogador {riot_id}#{tagline} não está registrado.")

# Tratamento de erro para o caso de um usuário sem permissões tentar usar o comando
@test_embed.error
async def test_embed_error(interaction: discord.Interaction, error):
    if isinstance(error, commands.MissingPermissions):
        await interaction.response.send_message("Você não tem permissão para usar este comando. Apenas administradores podem utilizá-lo.")

# Evento que inicia o monitoramento após o bot ser ativado
@client.event
async def on_ready():
    logging.info(f"Logado como {client.user}")
    asyncio.create_task(monitor_all_matches())

client.run(DISCORD_TOKEN)
