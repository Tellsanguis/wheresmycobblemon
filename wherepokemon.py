import discord
import pandas as pd
from discord.ext import commands
from discord import app_commands
import os
import logging
import re
import textwrap

# Configuration du système de journalisation pour suivre l'activité du bot
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

# Récupération des variables d'environnement nécessaires au fonctionnement du bot
TOKEN = os.getenv("DISCORD_BOT_TOKEN")  # Token d'authentification du bot Discord
GUILD_ID = int(os.getenv("DISCORD_GUILD_ID", "0"))  # ID du serveur Discord
EXCEL_FILE = "/documents/mes_donnees.xlsx"  # Chemin du fichier Excel contenant les données Pokémon

# Vérification que l'ID du serveur Discord est configuré
if GUILD_ID == 0:
    logging.error("❌ DISCORD_GUILD_ID n'est pas défini. Vérifie tes variables d'environnement.")
    exit(1)

# Variable globale pour stocker les données de spawn des Pokémon
spawn_data = []

def load_spawn_data_from_excel():
    """
    Charge les données de spawn des Pokémon depuis le fichier Excel.
    Les données sont stockées dans la variable globale spawn_data.
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
    Gère de manière sécurisée l'affichage des valeurs des champs.
    
    Args:
        val: Valeur à sécuriser pour l'affichage
        
    Returns:
        Une représentation textuelle sécurisée de la valeur
    """
    try:
        # Gestion des valeurs NaN de pandas
        if pd.isna(val):
            return "∅"
    except Exception:
        pass
    # Conversion des booléens en chaînes de caractères
    if isinstance(val, bool):
        return str(val).lower()
    val_str = str(val)
    # Remplacement des chaînes vides ou "nan" par un symbole spécial
    if val_str.strip() == "" or val_str.lower() == "nan":
        return "∅"
    return val_str

def split_long_field(label, emoji, value, max_length=1700):
    """
    Divise un champ trop long en plusieurs parties pour respecter les limites de Discord.
    
    Args:
        label: Le nom du champ
        emoji: L'emoji à utiliser
        value: La valeur du champ
        max_length: Longueur maximale par message
        
    Returns:
        Une liste de chaînes, chacune contenant une partie du champ
    """
    if len(value) <= max_length:
        return [f"{emoji} **{label}** : {value}"]
    
    # Diviser la liste des valeurs (par exemple, liste de biomes)
    items = [item.strip() for item in value.split(',')]
    
    parts = []
    current_part = []
    current_length = 0
    base_prefix = f"{emoji} **{label}** : "
    cont_prefix = f"{emoji} **{label} (suite)** : "
    
    for item in items:
        # Tenir compte des préfixes dans le calcul de la longueur
        prefix = base_prefix if not current_part else cont_prefix
        # +2 pour la virgule et l'espace
        item_length = len(item) + 2
        
        # Si ajouter cet élément dépasse la limite, commencer une nouvelle partie
        if current_part and (current_length + item_length + len(prefix) > max_length):
            parts.append(prefix + ", ".join(current_part))
            current_part = [item]
            current_length = item_length
        else:
            current_part.append(item)
            current_length += item_length
    
    # Ajouter la dernière partie
    if current_part:
        prefix = base_prefix if not parts else cont_prefix
        parts.append(prefix + ", ".join(current_part))
    
    return parts

def prepare_message_parts(fields_output, header, max_length=1900):
    """
    Prépare les parties du message à envoyer pour respecter les limites de Discord.
    
    Args:
        fields_output: Liste des champs à inclure
        header: En-tête du message
        max_length: Longueur maximale par message
        
    Returns:
        Une liste de chaînes, chacune correspondant à une partie du message
    """
    message_parts = []
    current_part = header
    
    for field in fields_output:
        # Si ce champ fait dépasser la longueur maximale, commencer une nouvelle partie
        if len(current_part + "\n" + field) > max_length:
            message_parts.append(current_part)
            current_part = field
        else:
            if current_part == header:
                current_part += field
            else:
                current_part += "\n" + field
    
    # Ajouter la dernière partie
    if current_part:
        message_parts.append(current_part)
    
    return message_parts

# Configuration des permissions et fonctionnalités du bot Discord
intents = discord.Intents.default()
intents.message_content = True  # Permet au bot de lire le contenu des messages

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.tree.command(guild=discord.Object(id=GUILD_ID), name="where", description="Affiche les conditions de spawn d'un Pokémon")
@app_commands.describe(pokemon="Nom du Pokémon recherché", show_all="Afficher tous les champs (même vides)")
async def where(interaction: discord.Interaction, pokemon: str, show_all: bool = False):
    """
    Commande slash pour afficher les conditions de spawn d'un Pokémon.
    
    Args:
        interaction: L'interaction Discord
        pokemon: Le nom du Pokémon recherché
        show_all: Booléen pour afficher tous les champs, même vides
    """
    # Recherche du Pokémon dans les données chargées
    results = [entry for entry in spawn_data if safe_field(entry.get("Pokemon")).lower() == pokemon.lower()]
    if not results:
        await interaction.response.send_message(f"❌ Aucune information trouvée pour **{pokemon}**.", ephemeral=True)
        return
    
    # Répondre d'abord pour éviter le timeout de Discord (3 secondes)
    await interaction.response.send_message(f"Recherche d'informations sur **{pokemon}**...", ephemeral=True)
    
    # Traiter chaque entrée correspondant au Pokémon (peut être plusieurs)
    for entry_index, entry in enumerate(results):
        header = f"🔍 **Informations sur {safe_field(entry.get('Pokemon'))} (Entrée {entry_index+1}/{len(results)})**\n"
        fields_output = []
        
        # Définition des champs à afficher avec leurs emojis
        field_mapping = [
            ("Rareté", "📌", "Bucket"),
            ("Dimensions", "🌍", "Dimensions"),
            ("Structures", "🏰", "Structures"),
            ("Phase de Lune", "🌙", "Moon Phase"),
            ("Can See Sky", "☀️", "Can See Sky"),
            ("Min X", "⬅️", "Min X"),
            ("Min Y", "⬇️", "Min Y"),
            ("Min Z", "↙️", "Min Z"),
            ("Max X", "➡️", "Max X"),
            ("Max Y", "⬆️", "Max Y"),
            ("Max Z", "↗️", "Max Z"),
            ("Min Light", "💡", "Min Light"),
            ("Max Light", "💡", "Max Light"),
            ("Min Sky Light", "🌤️", "Min Sky Light"),
            ("Max Sky Light", "🌤️", "Max Sky Light"),
            ("Time Range", "⏰", "Time Range"),
            ("Is Raining", "☔", "Is Raining"),
            ("Is Thundering", "⚡", "Is Thundering"),
            ("Is Slime Chunk", "🟢", "Is Slime Chunk"),
            ("Labels", "🏷️", "Labels"),
            ("Label Mode", "📋", "Label Mode"),
            ("Min Width", "📏", "Min Width"),
            ("Max Width", "📐", "Max Width"),
            ("Min Height", "↕️", "Min Height"),
            ("Max Height", "↕️", "Max Height"),
            ("Needed Nearby Blocks", "🧱", "Needed Nearby Blocks"),
            ("Needed Base Blocks", "🧱", "Needed Base Blocks"),
            ("Min Depth", "⚓", "Min Depth"),
            ("Max Depth", "⚓", "Max Depth"),
            ("Fluid Is Source", "🔄", "Fluid Is Source"),
            ("Fluid Block", "🌊", "Fluid Block"),
            ("Key Item", "🔑", "Key Item"),
            ("Stone Requirements", "🪨", "Stone Requirements"),
            ("Custom Pokemons In Team", "👥", "Custom Pokemons In Team"),
        ]
        
        # Traiter tous les champs normaux
        for label, emoji, field_name in field_mapping:
            value = safe_field(entry.get(field_name))
            if show_all or (value != "∅" and value):
                fields_output.append(f"{emoji} **{label}** : {value}")
        
        # Traitement spécial pour le champ biomes qui peut être très long
        biomes_value = safe_field(entry.get("Biomes"))
        if show_all or (biomes_value != "∅" and biomes_value):
            biomes_parts = split_long_field("Biomes", "🏞️", biomes_value)
            fields_output.extend(biomes_parts)
        
        # Message par défaut si aucune information n'est disponible
        if not fields_output:
            fields_output.append("Aucune information spécifique n'est disponible pour ce Pokémon.")
        
        # Préparer les parties du message pour respecter la limite de caractères de Discord
        all_parts = prepare_message_parts(fields_output, header)
        
        # Envoyer chaque partie du message
        for i, part in enumerate(all_parts):
            part_indicator = f" (Partie {i+1}/{len(all_parts)})" if len(all_parts) > 1 else ""
            try:
                await interaction.followup.send(part + part_indicator, ephemeral=True)
            except discord.errors.HTTPException as e:
                # En cas d'erreur, découper davantage le message
                logging.error(f"Erreur lors de l'envoi du message (longueur: {len(part)}): {e}")
                # Si le message est encore trop long, le diviser davantage
                chunks = textwrap.wrap(part, width=1900, replace_whitespace=False, break_long_words=True)
                for j, chunk in enumerate(chunks):
                    sub_indicator = f" (Partie {i+1}.{j+1}/{len(all_parts)}.{len(chunks)})"
                    await interaction.followup.send(chunk + sub_indicator, ephemeral=True)

@where.autocomplete("pokemon")
async def pokemon_autocomplete(interaction: discord.Interaction, current: str):
    """
    Fonction d'autocomplétion pour la commande where.
    Suggère des noms de Pokémon basés sur le texte saisi.
    
    Args:
        interaction: L'interaction Discord
        current: Le texte actuellement saisi par l'utilisateur
        
    Returns:
        Une liste de suggestions pour l'autocomplétion
    """
    # Récupérer tous les noms de Pokémon disponibles dans les données
    names = {safe_field(entry.get("Pokemon")) for entry in spawn_data if safe_field(entry.get("Pokemon")) != "∅"}
    names = sorted(names)
    # Filtrer et limiter les résultats à 25 selon les restrictions de Discord
    return [
        app_commands.Choice(name=name, value=name)
        for name in names if current.lower() in name.lower()
    ][:25]  # Discord limite à 25 options maximum

@bot.event
async def on_ready():
    """
    Fonction appelée lorsque le bot est connecté et prêt.
    Charge les données et synchronise les commandes slash.
    """
    # Charger les données depuis le fichier Excel
    load_spawn_data_from_excel()
    guild = discord.Object(id=GUILD_ID)
    try:
        # Synchroniser les commandes slash pour qu'elles apparaissent dans Discord
        synced = await bot.tree.sync(guild=guild)
        logging.info(f"{len(synced)} commandes synchronisées sur le serveur {guild.id}.")
    except Exception as e:
        logging.error(f"Erreur de synchronisation des commandes : {e}")
    logging.info(f"✅ Bot connecté en tant que {bot.user}")

# Démarrer le bot avec le token fourni
bot.run(TOKEN)
