# Cadrage de l'alpha StoneBench

Ce cadrage fonctionnel a été confirmé par l'utilisateur le 8 octobre 2026, à l'issue de l'entretien grill-with-docs. Il consolide les décisions prises pendant les questions Q1–Q37 et leur confirmation finale. Les contrats techniques et la faisabilité de plusieurs garanties restent à établir avant implémentation.

## Résumé confirmé

StoneBench fournit des outils MCP à un agent exécuté dans Inspect AI pour construire des portes regular DOOR sur un serveur Minecraft Java 1.21.11 dédié. Chaque tentative commence dans une zone vide ; la tâche fixe le passage et l'agent construit aussi l'encadrement. La campagne comprend huit tâches : quatre tailles (2×2, 3×3, 4×4, 5×5), chacune avec un objectif de volume minimal ou d'ouverture la plus rapide.

Le vérificateur expose tous les résultats à l'agent. Il teste au maximum cinq cycles par répéteur, avec arrêt au premier retour à l'état 0, puis un cycle direct depuis le même état 0 ; les états ouverts et fermés du premier cycle sont comparés entre modes, données internes et inventaires compris. Chaque transition est bornée à 36 000 ticks. Les essais utilisent une copie temporaire pour préserver la construction de l'agent.

L'alpha exclut les constructions avec entités et les portes nécessitant une horloge interne. Elle certifie uniquement son protocole fonctionnel et la définition regular DOOR, sans certifier toute l'admissibilité aux records communautaires. Le budget de tokens comprend une réserve de finalisation durant laquelle l'agent consulte, vérifie et soumet son meilleur checkpoint, achevé ou non. Sans choix final, le statut est « aucune soumission ».

## Décisions confirmées

- Le projet sert à la fois à assister les agents dans la construction et à comparer les modèles par une évaluation reproductible.
- Chaque construction commence dans une zone vide.
- L'agent construit également l'encadrement physique. La tâche fournit un repère et les dimensions du passage, sans encadrement préconstruit (Q30). Le terme « cadre » du référentiel reste la section géométrique occupée par les blocs de porte fermée.
- La vérification automatique alpha porte sur les portes « regular DOOR », sans motif ni restriction spécifique de catégorie ; la taille demandée peut varier. Les skydoors et les constructions utilisant des entités sont hors du périmètre de cette alpha. Les données internes et inventaires des blocs sont pris en charge.
- Le résultat positif est libellé « conforme au protocole alpha » (Q37). Il couvre la définition de regular DOOR et le protocole fonctionnel convenu ; il ne certifie pas l'ensemble des conditions d'admissibilité aux records de la section 3 du référentiel. Les règles communautaires non couvertes sont explicitement indiquées « non vérifiées », sans être présentées comme réussies ou échouées.
- L'exécution repose sur un serveur Minecraft Java dédié, en version 1.21.11, et non sur un simulateur redstone indépendant.
- La tâche fixe le passage, son plan et les dimensions attendues ; l'agent organise librement sa construction autour.
- La première campagne comprend uniquement les tailles 2×2, 3×3, 4×4 et 5×5 (Q31).
- L'alpha utilise des observations textuelles. Un outil ultérieur pourrait produire une image depuis des coordonnées précises ; il n'est pas requis pour l'alpha.
- L'avancement de ticks retourne par défaut un diff entre les états initial et final ; une trace tick par tick est optionnelle.
- Le budget de tentative est exprimé en tokens, sans quota global de ticks. Chaque avancement est plafonné à 6 000 ticks (5 minutes de jeu à 20 ticks/s). La vérification autorise jusqu'à 36 000 ticks par transition, avec arrêt anticipé dès sa fin. Le protocole comporte au maximum 5 cycles avec répéteur, avec arrêt dès le premier retour à l'état initial (au plus 360 000 ticks), et 1 cycle direct depuis le même état initial (au plus 72 000 ticks). Le plafond dérivé est donc de 432 000 ticks de transition ; aucun plafond total indépendant n'est ajouté. La préparation des essais et la restauration sont distinctes de ces transitions.
- L'exécution accélérée avec `tick sprint` est souhaitée, sous réserve de vérifier le gel final et les observations. L'utilisateur rapporte environ 2 500 ticks/s sur son ordinateur ; cette mesure n'est pas une performance vérifiée par StoneBench ni une garantie de débit avec les traces actives.
- La conformité est la mesure principale. Le volume et la vitesse sont des objectifs secondaires séparés : l'utilisateur veut pousser chacun, sans les fusionner en un score unique, car améliorer l'un se fait souvent au détriment de l'autre.
- Chaque taille donne lieu à deux tâches distinctes : minimiser le volume et minimiser le temps d'ouverture. Toutes les tentatives mesurent néanmoins le volume et les temps ; la conformité reste obligatoire (Q33).
- À l'approche de la limite de tokens, le harness demande à l'agent de soumettre son meilleur checkpoint, terminé ou non. Cette sélection est faite par l'agent ; le harness ne choisit pas automatiquement une construction à sa place (Q34). Une réserve comprise dans le budget total doit couvrir cette finalisation ; son calcul et son déclenchement restent à calibrer techniquement.
- Pendant la finalisation, seuls la consultation, la vérification et la soumission sont autorisées ; l'agent ne modifie plus la construction (Q35).
- Si l'agent ne désigne aucun checkpoint malgré la demande de finalisation, la tentative se termine avec le statut « aucune soumission ». Les checkpoints et diagnostics sont conservés, sans sélection automatique d'une solution (Q36).
- Les règles et dénominations proviennent du [document de référence fourni par l'utilisateur](https://docs.google.com/document/d/1kDNXIvQ8uAMU5qRFXIk6nLxbVliIjcMu1MjHjLJrRH4/edit?usp=sharing), intitulé « Door Rules / Squid Records - Rules ». Les sections de catégorisation et de terminologie ont pu être consultées dans le navigateur après un refus 403 du connecteur. La lecture complète reste à terminer ; copie et export sont désactivés sur le document.
- Les résultats de conformité sont accessibles à l'agent. L'évaluation finale ne repose pas sur des critères de conformité cachés.
- Les checkpoints doivent être pris dans un état stable au repos pour l'alpha. Une porte nécessitant une horloge interne est considérée comme invalide dans cette alpha (Q25). Le référentiel communautaire admet plus largement certains états périodiques ; cette restriction est propre au périmètre retenu. Le moyen de reconnaître le repos et de restaurer fidèlement cet état reste à établir techniquement.
- La restauration fidèle de l'état d'exécution est l'objectif retenu, sous réserve d'une étude de faisabilité. Une simple copie des blocs ne suffit pas à établir cette fidélité.
- La vérification utilise une copie temporaire du checkpoint ; l'agent retrouve sa construction et son état d'avant l'appel. Les essais directs et par répéteur partent chacun du même état initial restauré (Q29), sous réserve de valider techniquement cette fidélité.
- Le référentiel est associé à la version Minecraft : on conserve le même document tant que cette version ne change pas. L'utilisateur précise que les changements communautaires de règles sont volontairement très rares.
- StoneBench fournit les outils Minecraft à un agent exécuté dans Inspect AI, via une interface MCP (Q24). Inspect AI gère la tentative et les appels au modèle ; les outils StoneBench contrôlent le serveur et produisent les résultats de conformité. Cette interface permet aussi une réutilisation des outils dans d'autres harness compatibles MCP.

## Entrée et construction par lots

- L'agent choisit un levier, un bouton en pierre ou un bouton en bois.
- Ce dispositif est à l'extérieur du volume mesuré, posé sur la surface d'un côté de la construction ; les placements sur le haut ou le bas sont exclus.
- Le fonctionnement par entrée directe et par répéteur doit être vérifié. L'utilisateur souligne le bug décrit par le référentiel : une action directe de joueur peut retirer un tick de délai aux composants redstone concernés. La reproduction de ces deux modes dans le contrôleur reste à établir.
- Un lot de blocs est placé intégralement avant transmission des mises à jour aux voisins, puis les mises à jour sont transmises dans l'ordre de la liste. Les callbacks de placement et le comportement lorsque les notifications sont désactivées restent à préciser techniquement.

## Retour à l'état initial

Le protocole précisé en Q26–Q28 comporte au maximum 5 cycles complets ouverture/fermeture avec répéteur. Chaque ouverture et fermeture doit satisfaire les critères géométriques et atteindre la fin de transition. Après chaque cycle, l'état fermé est comparé à l'état initial (état 0). Dès le premier retour à l'état 0, cette séquence s'arrête : poursuivre rejouerait une séquence déjà observée. Sans retour au terme du cinquième cycle, le protocole alpha conclut à un échec.

Un cycle d'entrée directe est testé séparément depuis le même état 0 restauré. Son état ouvert et son état fermé doivent être identiques aux états ouverts et fermés du premier cycle avec répéteur. L'état comparé inclut les blocs, les inventaires et les données internes de la construction ; les durées des deux modes peuvent différer. L'horloge globale du monde est enregistrée séparément. Les éventuelles normalisations de champs internes temporels devront être justifiées par leur préservation du comportement, sans ignorer les données qui affectent la suite de l'exécution.

La commande suivante attend la fin de la transition : plus rien ne change, et aucun événement programmé ne reste en attente. Une horloge interne nécessaire au fonctionnement est invalide pour l'alpha. La reconnaissance de l'absence de changement doit encore être précisée pour les composants actifs sans événement programmé et pour les changements retardés. Le test alpha constitue un critère borné de répétabilité, et non une preuve universelle de la fiabilité de toute construction vanilla.

## Actions souhaitées

- Vérifier la conformité et retourner les critères satisfaits et non satisfaits.
- Maintenir le jeu gelé par défaut, avancer de n ticks et observer les changements de blocs.
- Sauvegarder plusieurs copies d'une construction.
- Lire l'état de blocs désignés par leurs coordonnées.
- Modifier une liste de blocs, y compris leur suppression par remplacement avec de l'air, avec une option de mise à jour des voisins.
- Lire les données internes des blocs et modifier les paramètres configurables en jeu, notamment leurs inventaires. Les états de fonctionnement sont calculés par Minecraft (Q32).
- Déclarer et actionner le dispositif d'entrée pour les essais.

## Paramètres configurables et états de fonctionnement

La règle retenue est d'autoriser la configuration d'une construction réalisable en jeu, sans permettre à l'agent d'injecter librement tous les états internes du moteur. Les interactions normales avec le dispositif d'entrée passent par un outil d'action.

| Élément | Paramètres configurables | États calculés par Minecraft, en lecture seule |
| --- | --- | --- |
| Pose d'un bloc | Type, coordonnées, orientation et face de pose compatibles avec le bloc | Connexions et états actualisés par les voisins |
| Répéteur | Orientation et réglage du délai | Alimentation et verrouillage par les entrées redstone |
| Comparateur | Orientation et mode comparaison/soustraction | Puissance de sortie et état alimenté |
| Pistons | Type normal/collant et orientation | Extension, tête et progression du mouvement |
| Blocs à inventaire | Contenu des slots, types et quantités d'objets valides | Cooldowns et transferts pendant le fonctionnement |
| Levier ou bouton d'entrée | Type, emplacement et face latérale de pose | Signal et durée d'activation produits par l'interaction normale |

Cette table décrit le principe retenu pour les réglages, pas une liste fermée de blocs autorisés. Les propriétés de délai, orientation, alimentation et verrouillage du répéteur ainsi que le mode du comparateur figurent dans les [mappings Java 1.21.11](https://maven.fabricmc.net/docs/yarn-1.21.11%2Bbuild.3/net/minecraft/state/property/Properties.html). Le chemin de configuration devra préserver les notifications vanilla et l'ordre des lots convenu.

Les puissances de signal, états de verrouillage produits par la redstone, mouvements de pistons, cooldowns et files d'événements sont observables mais ne sont pas directement éditables. La liste exacte des paramètres autorisés par type de bloc doit être établie à partir des configurations accessibles en jeu sur 1.21.11 ; ces exemples ne constituent pas une liste fermée de blocs autorisés.

Le diff final et la trace optionnelle sont retenus. La restauration des checkpoints, les observations exactes dans une trace et les modalités de propagation après un lot restent à préciser.

## Motivation exprimée par l'utilisateur

La communauté produit régulièrement de nouveaux designs et records, avec des catégories et notations très réglementées. Selon l'utilisateur, une grande partie des constructions n'est disponible en ligne que sous forme de captures d'écran. StoneBench vise à exploiter ce domaine pour évaluer la résolution de problèmes et la représentation spatiale et relationnelle en trois dimensions.

Une solution inhabituelle qui respecte les règles doit être acceptée ; une erreur du vérificateur doit être corrigée. Le caractère déterministe attendu de la vérification ne remplace pas la nécessité de définir et d'implémenter correctement les critères.

## État constaté du dépôt

Le checkout contient un point de départ Python et un import de `litemapy` dans `src/first_tests.py`. Aucun contrôle de Minecraft ni simulateur redstone n'a été identifié. Des suppressions locales et des fichiers non suivis préexistaient à l'entretien.

## Travaux techniques restant à résoudre

Ces travaux ne remettent pas en question le cadrage fonctionnel retenu. Ils doivent établir les contrats exacts et démontrer les garanties demandées ; une limite technique ne doit pas être masquée par une réduction silencieuse du protocole.

- Terminer la lecture des définitions pertinentes du référentiel et établir la table des critères alpha couverts, des exclusions de périmètre et des règles communautaires non vérifiées.
- Interface de contrôle du serveur Minecraft Java 1.21.11 et connexion MCP à Inspect AI.
- Format des demandes, convention du repère fixé et déclaration de l'entrée de la porte.
- Reconnaissance de la fin des transitions, incluant les composants actifs hors des files d'événements.
- Reproduction technique des entrées directe et par répéteur selon le dispositif choisi.
- Contenu et restauration des checkpoints.
- Sémantique des modifications et de l'observation des ticks.
- Méthodes de mesure du volume et de la vitesse, et calibration des budgets comparables entre modèles, y compris la réserve de finalisation.
- Détail des observations textuelles, des traces et des limites par opération.
