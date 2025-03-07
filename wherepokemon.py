import discord
import pandas as pd
from discord.ext import commands
from discord import app_commands
import os
import logging
import re

# Configuration du logging pour suivre l'activité du bot
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

# Récupération des variables d'environnement pour la configuration
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GUILD_ID = int(os.getenv("DISCORD_GUILD_ID", "0"))
EXCEL_FILE = "/documents/mes_donnees.xlsx"
TAGS_FILE = "/documents/biomes_tags.txt"

# Vérification que l'ID du serveur Discord est bien défini
if GUILD_ID == 0:
    logging.error("❌ DISCORD_GUILD_ID n'est pas défini. Vérifie tes variables d'environnement.")
    exit(1)

# Variables globales pour stocker les données de spawn et les tags de biome
spawn_data = []
BIOME_TAGS = {}

# Charge le fichier TXT contenant le tableau ASCII et construit un mapping des tags
def load_biome_tags():
    """
    Charge et analyse un fichier texte contenant un tableau ASCII de correspondances
    entre les tags de biome et les noms de biome Minecraft
    """
    mapping = {}
    try:
        with open(TAGS_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        # On ignore les lignes qui ne commencent pas par "|" ou qui sont des bordures
        for line in lines:
            line = line.strip()
            if not line or line.startswith("+") or "Registry name" in line:
                continue
            if line.startswith("|"):
                parts = line.split("|")
                if len(parts) < 4:
                    continue
                registry = parts[2].strip()
                tags_field = parts[3].strip()
                if not registry or not tags_field:
                    continue
                # Traitement des tags pour chaque biome
                tags = [t.strip() for t in tags_field.split(",") if t.strip()]
                for tag in tags:
                    if not tag.startswith("#"):
                        tag = "#" + tag
                    if tag not in mapping:
                        mapping[tag] = []
                    if registry not in mapping[tag]:
                        mapping[tag].append(registry)
    except Exception as e:
        logging.error(f"Erreur lors de la lecture du fichier des tags: {e}")
    return mapping

# Fonction récursive pour résoudre un tag en une liste de biomes
def resolve_tag(tag, mapping, seen=None):
    """
    Résout récursivement un tag de biome en une liste de biomes spécifiques
    Gère les références circulaires avec l'ensemble 'seen'
    """
    if seen is None:
        seen = set()
    # Évite les boucles infinies en gardant trace des tags déjà vus
    if tag in seen:
        return []
    seen.add(tag)
    
    if tag in mapping:
        result = []
        for item in mapping[tag]:
            # Si l'élément est lui-même un tag, résolution récursive
            if item.startswith("#") and "is_" in item:
                result.extend(resolve_tag(item, mapping, seen))
            else:
                result.append(item)
        return result
    else:
        # Tentative de remplacement de préfixes pour gérer différentes notations de tags
        prefixes = ["#biome:", "#minecraft:", "#cobblemon:"]
        for p in prefixes:
            if tag.startswith(p):
                remainder = tag[len(p):]
                for alt in prefixes:
                    new_tag = alt + remainder
                    if new_tag in mapping:
                        return resolve_tag(new_tag, mapping, seen)
        # Si aucune correspondance n'est trouvée, retourne le tag sans le # comme biome
        return [tag.lstrip("#")]

# Remplace dans une chaîne tous les tags par la liste de biomes correspondants
def resolve_biomes(biomes_str, mapping):
    """
    Analyse une chaîne contenant plusieurs tags/biomes séparés par des virgules
    et résout chaque tag en une liste de biomes spécifiques
    """
    if not biomes_str or biomes_str == "∅":
        return biomes_str
    
    # Sépare la chaîne en parties individuelles
    parts = [part.strip() for part in biomes_str.split(",")]
    resolved_parts = []
    
    # Traite chaque partie individuellement
    for part in parts:
        if "is_" in part:  # C'est probablement un tag
            if not part.startswith("#"):
                part = "#" + part
            resolved = resolve_tag(part, mapping)
            if resolved:
                resolved_parts.extend(resolved)
            else:
                resolved_parts.append(part.lstrip("#"))
        else:
            resolved_parts.append(part)
    
    # Élimine les doublons et trie les résultats
    resolved_parts = sorted(set(resolved_parts))
    return ", ".join(resolved_parts)

def load_spawn_data_from_excel():
    """
    Charge les données de spawn depuis le fichier Excel
    """
    global spawn_data
    try:
        df = pd.read_excel(EXCEL_FILE)
        spawn_data = df.to_dict(orient="records")
        logging.info(f"Données chargées depuis {EXCEL_FILE}. {len(spawn_data)} entrées disponibles.")
    except Exception as e:
        logging.error(f"Erreur lors du chargement du fichier Excel: {e}")
        spawn_data = []

def safe_field(val):
    """
    Normalise les valeurs des champs pour l'affichage
    Gère les valeurs nulles, NaN, vides, booléennes
    """
    try:
        if pd.isna(val):
            return "∅"
    except Exception:
        pass
    if isinstance(val, bool):
        return str(val).lower()
    val_str = str(val)
    if val_str.strip() == "" or val_str.lower() == "nan":
        return "∅"
    return val_str

# Configuration des intentions Discord nécessaires
intents = discord.Intents.default()
intents.message_content = True

# Initialisation du bot Discord
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.tree.command(guild=discord.Object(id=GUILD_ID), name="where", description="Affiche les conditions de spawn d'un Pokémon")
@app_commands.describe(pokemon="Nom du Pokémon recherché")
async def where(interaction: discord.Interaction, pokemon: str):
    """
    Commande slash Discord pour afficher les conditions de spawn d'un Pokémon spécifique
    """
    # Recherche du Pokémon dans les données chargées (insensible à la casse)
    results = [entry for entry in spawn_data if safe_field(entry.get("Pokemon")).lower() == pokemon.lower()]
    
    if not results:
        await interaction.response.send_message(f"❌ Aucune information trouvée pour **{pokemon}**.", ephemeral=True)
        return
    
    messages = []
    for entry in results:
        # Construction de l'en-tête du message
        header = f"🔍 **Informations sur {safe_field(entry.get('Pokemon'))}**\n"
        fields_output = []
        
        # Fonction helper pour ajouter un champ formaté au message
        def add_field(label, emoji, value):
            if value != "∅":
                fields_output.append(f"{emoji} **{label}** : {value}")
        
        # Ajout des différents champs avec leur emoji correspondant
        add_field("Rareté", "📌", safe_field(entry.get("Bucket")))
        add_field("Dimensions", "🌍", safe_field(entry.get("Dimensions")))
        
        # Résolution des tags de biome en noms de biomes spécifiques
        biomes_raw = safe_field(entry.get("Biomes"))
        biomes_resolved = resolve_biomes(biomes_raw, BIOME_TAGS)
        add_field("Biomes", "🏞️", biomes_resolved)
        
        add_field("Structures", "🏰", safe_field(entry.get("Structures")))
        add_field("Phase de Lune", "🌙", safe_field(entry.get("Moon Phase")))
        add_field("Can See Sky", "☀️", safe_field(entry.get("Can See Sky")))
        add_field("Min X", "⬅️", safe_field(entry.get("Min X")))
        add_field("Min Y", "⬇️", safe_field(entry.get("Min Y")))
        add_field("Min Z", "↙️", safe_field(entry.get("Min Z")))
        add_field("Max X", "➡️", safe_field(entry.get("Max X")))
        add_field("Max Y", "⬆️", safe_field(entry.get("Max Y")))
        add_field("Max Z", "↗️", safe_field(entry.get("Max Z")))
        add_field("Min Light", "💡", safe_field(entry.get("Min Light")))
        add_field("Max Light", "💡", safe_field(entry.get("Max Light")))
        add_field("Min Sky Light", "🌤️", safe_field(entry.get("Min Sky Light")))
        add_field("Max Sky Light", "🌤️", safe_field(entry.get("Max Sky Light")))
        add_field("Time Range", "⏰", safe_field(entry.get("Time Range")))
        add_field("Is Raining", "☔", safe_field(entry.get("Is Raining")))
        add_field("Is Thundering", "⚡", safe_field(entry.get("Is Thundering")))
        add_field("Is Slime Chunk", "🟢", safe_field(entry.get("Is Slime Chunk")))
        add_field("Labels", "🏷️", safe_field(entry.get("Labels")))
        add_field("Label Mode", "📋", safe_field(entry.get("Label Mode")))
        add_field("Min Width", "📏", safe_field(entry.get("Min Width")))
        add_field("Max Width", "📐", safe_field(entry.get("Max Width")))
        add_field("Min Height", "↕️", safe_field(entry.get("Min Height")))
        add_field("Max Height", "↕️", safe_field(entry.get("Max Height")))
        add_field("Needed Nearby Blocks", "🧱", safe_field(entry.get("Needed Nearby Blocks")))
        add_field("Needed Base Blocks", "🧱", safe_field(entry.get("Needed Base Blocks")))
        add_field("Min Depth", "⚓", safe_field(entry.get("Min Depth")))
        add_field("Max Depth", "⚓", safe_field(entry.get("Max Depth")))
        add_field("Fluid Is Source", "🔄", safe_field(entry.get("Fluid Is Source")))
        add_field("Fluid Block", "🌊", safe_field(entry.get("Fluid Block")))
        add_field("Key Item", "🔑", safe_field(entry.get("Key Item")))
        add_field("Stone Requirements", "🪨", safe_field(entry.get("Stone Requirements")))
        add_field("Custom Pokemons In Team", "👥", safe_field(entry.get("Custom Pokemons In Team")))
        
        # Assemblage du message complet
        msg = header + "\n".join(fields_output)
        messages.append(msg)
    
    # Concaténation de tous les résultats avec double saut de ligne entre chacun
    response = "\n\n".join(messages)
    await interaction.response.send_message(response, ephemeral=True)

@where.autocomplete("pokemon")
async def pokemon_autocomplete(interaction: discord.Interaction, current: str):
    """
    Gère l'autocomplétion des noms de Pokémon pour la commande /where
    """
    # Récupère tous les noms de Pokémon uniques dans les données
    names = {safe_field(entry.get("Pokemon")) for entry in spawn_data if safe_field(entry.get("Pokemon")) != "∅"}
    names = sorted(names)
    
    # Filtre les noms en fonction de la saisie actuelle et limite à 25 résultats (limite Discord)
    return [
        app_commands.Choice(name=name, value=name)
        for name in names if current.lower() in name.lower()
    ][:25]

@bot.event
async def on_ready():
    """
    Événement déclenché lorsque le bot est connecté et prêt
    """
    global BIOME_TAGS
    
    # Chargement des données nécessaires au démarrage
    BIOME_TAGS = load_biome_tags()
    logging.info(f"{len(BIOME_TAGS)} mappings de biome tags chargés depuis le fichier TXT.")
    load_spawn_data_from_excel()
    
    # Synchronisation des commandes slash avec Discord
    guild = discord.Object(id=GUILD_ID)
    try:
        synced = await bot.tree.sync(guild=guild)
        logging.info(f"{len(synced)} commandes synchronisées sur le serveur {guild.id}.")
    except Exception as e:
        logging.error(f"Erreur de synchronisation des commandes : {e}")
    
    logging.info(f"✅ Bot connecté en tant que {bot.user}")

# Démarrage du bot avec le token
bot.run(TOKEN)
