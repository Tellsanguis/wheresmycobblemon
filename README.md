# Wheresmycobblemon?!

# Spawn Data & Discord Bot

Ce projet se compose de deux scripts principaux :

- **extract.py**  
  Ce script extrait les données de spawn depuis tous les fichiers JSON situés dans les dossiers <ins>spawn_pool_world</ins> (par exemple dans un dossier global de datapacks) et les exportent dans un fichier .xlsx (Excel, libreOffice, tableur...). Il gère aussi la résolution des tags de biomes en remplaçant les identifiants (par exemple, `#minecraft:is_savanna_plateau`) par la liste des biomes correspondants grâce à un fichier de tags.

- **wherepokemon.py**  
  Ce script est un bot Discord qui lit le fichier .xlsx généré par <ins>*extract.py*</ins> et répond à la commande slash `/where` en affichant les conditions de spawn d'un Pokémon donné.

🔥UPDATE🔥
Le bot indique désormais l'endroit optimal où capturer votre pokemon !

## Fonctionnalités

- **Extraction de spawn**  
  - Parcours récursif de l'arborescence pour extraire les données JSON dans les dossiers *spawn_pool*.
  - Extraction des conditions de spawn de base (ex. Pokémon, Bucket, Dimensions, Biomes, Structures, etc.).
  - Extraction de conditions supplémentaires, notamment :
    - **Stone Requirements** : recherche de toutes les clés se terminant par `_stone_requirement` pour obtenir le nombre et le type de pierre d'évolution.
    - **Custom Pokemons In Team** : extraction des Pokémon spécifiques à avoir dans l'équipe avec leur nombre requis.
    - Conditions de profondeur (ex. `Min Y` et `Max Y`).
  - **Résolution des tags de biomes** en utilisant un fichier de tags au format TXT.

- **Bot Discord**  
  - Lecture du fichier .xlsx généré.
  - Commande slash `/where` qui affiche de manière privée (ephemeral) les conditions de spawn d'un Pokémon.
  - Autocomplete pour la commande afin de faciliter la saisie du nom de Pokémon.

- **Résolution des Biomes via Tags**  
  Le script **extract.py** utilise un fichier TXT (généré avec le mod [TellMe](https://modrinth.com/mod/tellme) via la commande `/tellme dump to-file ascii-table biomes-with-tags`) qui contient un tableau ASCII avec :
  - Une colonne *ID* (ignorée)
  - Une colonne *Registry name* (l'identifiant du biome)
  - Une colonne *Tags* (la liste des tags auxquels appartient ce biome)  
  Le script lit ce fichier et construit un mapping permettant de remplacer les tags dans les données (ex. `#minecraft:is_savanna_plateau`) par la liste des biomes correspondants.

## Prérequis

- Python 3.9 ou supérieur
- Modules Python nécessaires (voir `requirements.txt`) :
  - `pandas`
  - `discord.py`
  - `openpyxl`
- Le fichier zip avec les fichiers de configuration du spawn des pokemons de cobblemon (ici, pour la 1.5.2 : https://gitlab.com/cable-mc/cobblemon/-/archive/1.5.2/cobblemon-1.5.2.zip?path=common/src/main/resources/data/cobblemon/spawn_pool_world)
- Votre dossier de datapacks (global_packs par exemple, celui où vous avez AllTheMons ou autres datapacks ajoutant des pokemons)
- Vous mettrez votre dossier de datapacks et le contenu du fichier zip dans un même dossier
- Le fichier de tags des biomes, généré via le mod [TellMe](https://modrinth.com/mod/tellme) avec la commande : `/tellme dump to-file ascii-table biomes-with-tags`
  - Renommez le fichier généré en `biomes_tags.txt`
  - Puis placez-le dans le même dossier que `extract.py`.

## Installation

1. Clonez ce projet depuis GitHub.
2. Installez les dépendances avec la commande suivante :
 ```
 pip install -r requirements.txt
 ```

## Utilisation
**Extraction des Données**

Pour extraire les données depuis les fichiers JSON et générer un fichier .xlsx, utilisez le script extract.py (ou extract_and_merge.py si vous avez fusionné avec un tableur additionnel).

Exemple :
 ```
python extract.py /chemin/vers/dossier/globaldatapack --biome-tags ./biomes_tags.txt --output mes_donnees.xlsx
 ```

    /chemin/vers/dossier/globaldatapack : chemin vers le dossier racine contenant les datapacks et les fichiers JSON de Cobblemon
    --biome-tags : chemin vers votre fichier biomes_tags.txt
    --output mes_donnees.xlsx : nom du fichier .xlsx de sortie.

**Bot Discord**

Le script wherepokemon.py lit le fichier .xlsx généré et répond à la commande slash `/where`.

Variables importantes à configurer (via variables d'environnement ou directement dans le script) :

    DISCORD_BOT_TOKEN : Token de votre bot Discord.
    DISCORD_GUILD_ID : ID de votre serveur Discord (pour synchroniser rapidement la commande).
    EXCEL_FILE : Chemin vers le fichier .xlsx (par défaut /documents/mes_donnees.xlsx).

Exécutez le script :
 ```
python wherepokemon.py
 ```

La commande `/where` est disponible sur votre serveur et vous permet d'afficher les conditions de spawn pour un Pokémon donné.

## Docker

Un fichier docker-compose.yml est fourni pour exécuter le bot dans un conteneur Docker.

Exemple de docker-compose.yml :
 ```
version: '3.8'

services:
  wheresmypokemon:
    container_name: wheresmypokemon
    image: python:3.9
    environment:
      - DISCORD_BOT_TOKEN=
      - DISCORD_GUILD_ID=
    working_dir: /app
    volumes:
      - /sur/ton/hote/mes_donnees.xlsx:/documents/mes_donnees.xlsx
      - /sur/ton/hote:/app
    command: ["/bin/sh", "-c", "pip install -r /app/requirements.txt && python /app/wherepokemon.py"]
    restart: always
 ```

Pour lancer le bot via Docker :
 ```
docker-compose up -d
 ```
