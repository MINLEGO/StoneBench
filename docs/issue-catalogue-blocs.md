# Alléger la découverte des blocs et remplacer le catalogue de construction

## Problème et résultat attendu

`describe_blocks` renvoie actuellement tous les blocs avec leurs propriétés configurables, états calculés et capacités d’inventaire. L’agent doit recevoir ces détails même lorsqu’il cherche seulement les identifiants disponibles. Séparer la liste globale et le détail à la demande réduit le contenu des réponses de découverte.

Cette issue révise également les blocs effectivement pris en charge par `modify_blocks`, selon la liste fournie dans `docs/blocs-a-prendre-en-charge.md`. Le catalogue final est reproduit ci-dessous pour rendre l’issue autonome.

## Contrat de découverte

- Conserver `describe_blocks()` sans argument. Son contenu métier est uniquement une liste d’identifiants complets, uniques, ordonnés de façon déterministe : `{"catalog":["minecraft:air","minecraft:quartz_block",...]}`. Aucun détail de bloc, capacité d’inventaire ou énumération de propriétés dans cette réponse. L’enveloppe commune MCP suit le contrat en vigueur.
- Ajouter `describe_block(id)`, avec un identifiant exact obligatoire. Il renvoie un seul détail : `id`, `configurable`, `computed`, `inventory_slots`, ainsi que les annotations existantes sur les limites d’observation pertinentes pour ce bloc. Les valeurs de paramètres restent des chaînes.
- Un identifiant inconnu ou retiré renvoie `kind=unsupported`, `code=unsupported_component`. Aucun retour implicite du catalogue complet.
- Les deux outils sont des lectures sans mutation ni avance du temps. Le nouvel outil doit aussi être autorisé pendant une vérification, comme `describe_blocks` aujourd’hui.
- Ne pas ajouter de tutoriel redstone. Le modèle distingue les propriétés configurables des états calculés par Minecraft.
- Mettre à jour le schéma MCP, les listes d’outils de lecture et les instructions du harness pour demander les détails seulement lorsque nécessaires.

## Nouveau catalogue exclusif

Tous les identifiants ci-dessous portent le préfixe `minecraft:`. Cette liste de 70 blocs remplace entièrement le catalogue actuel ; les anciens identifiants absents deviennent non pris en charge par la construction.

```text
air
quartz_block
white_wool
orange_wool
magenta_wool
light_blue_wool
yellow_wool
lime_wool
pink_wool
gray_wool
light_gray_wool
cyan_wool
purple_wool
blue_wool
brown_wool
green_wool
red_wool
black_wool
obsidian
honey_block
sand
smooth_stone_slab
stone_stairs
glass
glass_pane
water
scaffolding
stone_brick_wall
player_head
beacon
oak_log
oak_leaves
piston
sticky_piston
observer
dispenser
dropper
repeater
comparator
redstone_wire
redstone_torch
redstone_wall_torch
stone_button
oak_button
lever
stone_pressure_plate
oak_pressure_plate
light_weighted_pressure_plate
heavy_weighted_pressure_plate
redstone_block
redstone_lamp
target
note_block
hopper
chest
trapped_chest
barrel
composter
iron_trapdoor
oak_trapdoor
iron_door
oak_door
oak_fence_gate
furnace
shulker_box
rail
powered_rail
detector_rail
activator_rail
waxed_copper_grate
```

Normalisations confirmées : `quartz` désigne `quartz_block`, toutes les laines désignent les 16 couleurs ci-dessus, et la torche murale désigne `redstone_wall_torch`.

## Construction des nouveaux blocs

### Blocs pouvant contenir de l’eau

Pour **chaque bloc du catalogue qui possède la propriété vanilla `waterlogged`**, exposer `waterlogged` dans `configurable` avec les valeurs `"true"` et `"false"`, et accepter ces valeurs dans `modify_blocks`. Cela concerne tous les blocs admissibles, pas seulement les trappes et `waxed_copper_grate`. La propriété ne doit plus être classée dans `computed` pour ces blocs.

Exemple : placer `minecraft:oak_trapdoor` avec `parameters: {"waterlogged":"true"}` crée une trappe contenant de l’eau. Une mise à jour avec `"false"` permet de retirer cette eau. Les mises à jour et ticks de fluide respectent le contrat existant de notifications et d’avance explicite du temps.

Un bloc ne possédant pas `waterlogged` refuse ce paramètre. Ne pas généraliser cette exception aux états électriques ou aux autres états internes.

### Eau libre

Le placement de `minecraft:water` crée une source. Les niveaux et écoulements sont ensuite calculés par Minecraft ; aucun paramètre permettant d’injecter un niveau d’écoulement. La simulation de l’eau utilise les ticks vanilla, sans avance implicite du temps dans `modify_blocks`.

### Portes à deux blocs

Une entrée `minecraft:oak_door` ou `minecraft:iron_door` désigne la position inférieure et crée automatiquement les deux moitiés cohérentes. L’agent n’a pas à soumettre la moitié supérieure.

Valider les deux emplacements, le support, les limites du monde et les conflits de coordonnées dans le lot avant toute mutation. Un conflit avec une autre entrée explicite ou une autre moitié générée refuse tout le lot. Installer les deux moitiés avant la phase de notifications ; rendre déterministe et documenter leur ordre dans cette phase. La construction ne doit pas permettre de forcer une moitié isolée via `half`.

### Paramètres et données internes

Conserver les réglages ordinaires de placement et les paramètres déjà pris en charge pour les blocs conservés. Définir et publier les réglages de placement des nouveaux blocs dans leur détail ; laisser Minecraft calculer les connexions et états électriques.

`player_head` est une tête sans profil personnalisé. Aucun ajout d’écriture de NBT, de composants d’item, de progression de piston, de cooldown, d’horodatage interne ou d’état électrique. Les nouveaux blocs à entité de bloc gardent les limites d’observation, de repos et de restauration tant que leur couverture n’a pas été établie.

L’ajout au catalogue est une couverture de construction, pas une preuve de conformité, de repos ou de restauration fidèle. Les erreurs de couverture ne deviennent pas des règles de conformité. La lecture des mondes, traces et checkpoints existants ne doit pas échouer simplement parce qu’ils contiennent un bloc désormais retiré de la construction.

## Critères d’acceptation et validation

- La liste globale correspond exactement aux 70 identifiants, sans doublon ni détail. Un appel de détail ne renvoie qu’un bloc et les identifiants retirés sont refusés en détail comme en construction.
- Les détails conservés gardent leurs valeurs configurables, états calculés, capacités d’inventaire et annotations pertinentes. Les inventaires des nouveaux blocs concernés sont décrits correctement.
- Tous les blocs du catalogue possédant `waterlogged` le publient comme configurable. Vérifier cette exhaustivité contre les propriétés du registre Minecraft, et tester les deux valeurs en construction sur un serveur réel, notamment trappe et grille de cuivre.
- Tester la source d’eau puis un écoulement après avance explicite ; vérifier qu’un niveau forcé est refusé et que la construction elle-même n’avance pas la simulation.
- Tester une porte de chaque matériau avec deux moitiés cohérentes ; tester un support invalide, une limite verticale et un conflit avec la moitié supérieure. Les échecs de validation ne modifient aucun bloc du lot.
- Vérifier le placement effectif et les contraintes spécifiques des nouveaux composants, notamment formes connectées, échafaudage et entités de bloc. Ajouter des fixtures significatives dans la suite d’intégration existante.
- Adapter les fixtures et tests qui utilisent des identifiants retirés. Vérifier les garanties existantes de validation atomique, de notifications ordonnées, de chunks préparés et de séparation entre lecture et simulation.
- Documenter l’incompatibilité du format de `describe_blocks`, le nouvel outil, le catalogue et les limites de couverture. Ne pas revendiquer un gain de tokens mesuré sans comparaison archivée des réponses avant/après.

## Zones concernées

`app/controller/src/main/java/stonebench/BlockCatalog.java`, `Construction.java`, `Controller.java`, `McpHttp.java`, les listes d’outils et instructions de `app/harness/inspect_task.py`, les tests de construction/entrée et les fixtures affectées, ainsi que `docs/controller.md` et la liste de blocs source.
