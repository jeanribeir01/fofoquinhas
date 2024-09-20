import discord
from discord import app_commands
import requests
import os
import random
import asyncio
from dotenv import load_dotenv

# Carregar variáveis do arquivo .env
load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
RIOT_API_KEY = os.getenv('RIOT_API_KEY')
GIPHY_API_KEY = os.getenv('GIPHY_API_KEY')  # Carregar a chave da API do Giphy

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
def get_account_info(riot_id, tagline):
    url = f"https://europe.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{riot_id}/{tagline}?api_key={RIOT_API_KEY}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Erro ao buscar conta: {response.status_code}, {response.text}")
    return None

# Função para obter as últimas 2 partidas do jogador
def get_recent_matches(puuid):
    url = f"https://americas.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?start=0&count=2&api_key={RIOT_API_KEY}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Erro ao buscar partidas: {response.status_code}, {response.text}")
    return None

# Função para obter os detalhes de uma partida
def get_match_details(match_id):
    url = f"https://americas.api.riotgames.com/lol/match/v5/matches/{match_id}?api_key={RIOT_API_KEY}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Erro ao buscar detalhes da partida {match_id}: {response.status_code}, {response.text}")
    return None

# Função para extrair informações relevantes da partida
def extract_match_info(match_data, puuid):
    participants = match_data['info']['participants']
    player_data = next((player for player in participants if player['puuid'] == puuid), None)

    if player_data:
        champion_name = player_data['championName']
        win_status = "🏆 DELICIIAAA" if player_data['win'] else "❌ KKKKKKKKKKKKKKKKKKKKK SE FUDEUUU"
        game_mode = match_data['info']['gameMode']  # Tipo de partida

        # Obter a versão atual do Data Dragon
        dd_version_url = "https://ddragon.leagueoflegends.com/api/versions.json"
        dd_version_response = requests.get(dd_version_url)
        if dd_version_response.status_code == 200:
            latest_version = dd_version_response.json()[0]
        else:
            latest_version = "12.10.1"  # Fallback para uma versão específica

        champion_image_url = f"http://ddragon.leagueoflegends.com/cdn/{latest_version}/img/champion/{champion_name}.png"
        kills = player_data['kills']
        deaths = player_data['deaths']
        assists = player_data['assists']

        return {
            "champion": champion_name,
            "status": win_status,
            "image_url": champion_image_url,
            "kda": f"{kills}/{deaths}/{assists}",
            "game_mode": game_mode  # Adiciona o tipo de partida
        }
    return None

# Função para obter um GIF aleatório de risadas
# Função para obter um GIF aleatório de risadas de memes brasileiros
def get_random_laugh_gif():
    # Modifica a query de busca para focar em risadas de memes brasileiros
    url = f"https://api.giphy.com/v1/gifs/search?api_key={GIPHY_API_KEY}&q=laugh&limit=50"
    response = requests.get(url)
    if response.status_code == 200:
        gifs = response.json()['data']
        if gifs:
            return random.choice(gifs)['images']['downsized_large']['url']  # Retorna um GIF aleatório
    return None  # Retorna None se não conseguir obter um GIF


# Função para monitorar partidas
async def monitor_matches(puuid, channel):
    last_match_id = None
    
    while True:
        match_ids = get_recent_matches(puuid)
        if match_ids:
            current_match_id = match_ids[0]  # Pega o ID da última partida
            
            if current_match_id != last_match_id:
                last_match_id = current_match_id
                
                match_data = get_match_details(current_match_id)
                if match_data:
                    match_info = extract_match_info(match_data, puuid)
                    embed = discord.Embed(
                        title=f"Tentou jogar de {match_info['champion']}",
                        description="PQPPPPPP",
                        color=discord.Color.blue()
                    )
                    embed.add_field(
                        name=f"{match_info['status']}",
                        value=f"KDA: {match_info['kda']}\n{match_info['game_mode']} de cria",
                        inline=False
                    )
                    embed.set_image(url=match_info['image_url'])

                    await channel.send(embed=embed)

        await asyncio.sleep(60)  # Espera 60 segundos antes de checar novamente

# Definir o comando /perfil para exibir detalhes das partidas
@client.tree.command(name="perfil", description="Mostrar perfil e últimas 2 partidas do jogador por Riot ID e Tagline")
@app_commands.describe(riot_id="Riot ID do jogador", tagline="Tagline do jogador")
async def perfil(interaction: discord.Interaction, riot_id: str, tagline: str):
    await interaction.response.defer()  # Evitar timeout
    account_info = get_account_info(riot_id, tagline)
    if account_info:
        puuid = account_info['puuid']
        match_ids = get_recent_matches(puuid)

        if match_ids:
            for match_id in match_ids:
                match_data = get_match_details(match_id)
                if match_data:
                    match_info = extract_match_info(match_data, puuid)
                    if match_info:
                        embed = discord.Embed(
                            title=f"Tentou jogar de {match_info['champion']}",
                            description=f"Quem praticou o crime: {interaction.user.mention}",
                            color=discord.Color.blue()
                        )
                        embed.add_field(
                            name=f"{match_info['status']}",
                            value=f"KDA: {match_info['kda']}\n{match_info['game_mode']} de cria",
                            inline=False
                        )
                        embed.set_image(url=match_info['image_url'])

                        # Verifica se o jogador perdeu e adiciona um GIF de risadas
                        if "❌ KKKKKKKKKKKKKKKKKKKKK SE FUDEUUU" in match_info['status']:
                            laugh_gif_url = get_random_laugh_gif()
                            if laugh_gif_url:
                                await interaction.followup.send(embed=embed)
                                await interaction.followup.send(laugh_gif_url)
                            else:
                                await interaction.followup.send(embed=embed)
                        else:
                            await interaction.followup.send(embed=embed)
                else:
                    await interaction.followup.send(f"Não foi possível obter os detalhes da partida {match_id}.")
        else:
            await interaction.followup.send("Não foi possível encontrar partidas recentes.")
    else:
        await interaction.followup.send("Conta não encontrada.")

# Comando para registrar um jogador e iniciar o monitoramento
@client.tree.command(name="registrar", description="Registrar um jogador para monitoramento de partidas")
@app_commands.describe(riot_id="Riot ID do jogador", tagline="Tagline do jogador")
async def registrar(interaction: discord.Interaction, riot_id: str, tagline: str):
    await interaction.response.defer()  # Evitar timeout
    account_info = get_account_info(riot_id, tagline)
    if account_info:
        puuid = account_info['puuid']
        await interaction.followup.send(f"Você foi registrado e será julgado!")
        await monitor_matches(puuid, interaction.channel)  # Inicia o monitoramento em segundo plano
    else:
        await interaction.followup.send("Conta não encontrada.")

client.run(DISCORD_TOKEN)