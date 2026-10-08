# Notes de lecture du référentiel

Source : [Door Rules / Squid Records - Rules](https://docs.google.com/document/d/1kDNXIvQ8uAMU5qRFXIk6nLxbVliIjcMu1MjHjLJrRH4/edit?usp=sharing), consulté le 8 octobre 2026 dans le navigateur, en mode Affichage. Ces notes sont partielles et ne remplacent pas la source.

- Section 2 : une construction est pilotée par un dispositif d'entrée unique ; chaque fonction doit être obtenue par une utilisation de ce dispositif.
- Sections 2.1 à 2.1.3 : le passage d'une porte à pistons est horizontal ou vertical et doit être prolongeable. La taille décrit la porte dans son cadre. `regular` est l'agencement par défaut ; la composition des blocs, l'orientation et les restrictions sont des dimensions distinctes de la classification.
- Section 2.1.3 : `DOOR` désigne une orientation face à un point cardinal ; `SKYDOOR` correspond à une orientation vers le haut ou le bas, avec des distinctions supplémentaires pour les trapdoors.
- Terminologie : les états ouvert et fermé sont des états stables. Le référentiel admet la récurrence périodique dans sa définition de stabilité. Une interaction avec le dispositif d'entrée transmet un signal permettant une transition vers un autre état stable.

## Admissibilité aux records (section 3)

L'entrée reconnue est un bouton en pierre, un bouton en bois ou un levier, placé sur la surface de la construction et soutenu par un bloc situé dans son volume. La construction doit fonctionner avec les modes d'entrée directe et par répéteur ; la source distingue aussi activation et désactivation selon le dispositif utilisé.

Les conditions comprennent une fiabilité durable, des transitions ayant une durée bornée et des utilisations illimitées, sans remise en état manuelle. Une dépendance à un état de sauvegarde particulier est donnée comme exemple non admissible. Le fonctionnement doit être vanilla, dans une version publiée de Minecraft Java, sans nécessiter de changement de version pendant la construction. Les mouvements d'un joueur dans le passage, ainsi que les composants non isolés décrits dans cette section, ne doivent pas provoquer de rupture de fonctionnement ou de stabilité, sous réserve des exceptions définies par le document.

Ces propriétés ne deviennent pas des preuves universelles simplement parce qu'un nombre fini de cycles est réussi. En Q37, l'utilisateur a retenu une alpha couvrant la définition regular DOOR et le protocole fonctionnel convenu, avec les autres règles communautaires indiquées « non vérifiées ». L'admissibilité complète aux records n'est donc pas certifiée par cette alpha.

Lecture complémentaire de la section 3 le 8 octobre 2026 : l'entrée doit pouvoir être reliée à distance en alimentant le bloc d'entrée depuis l'emplacement du dispositif. Avec un bouton, l'entrée dite directe combine une activation joueur et une désactivation par répéteur ; avec un levier, activation et désactivation sont des actions joueur. Les circuits ne doivent pas fonctionner seulement à certaines heures du jour. Les composants non isolés sont inadmissibles s'ils peuvent rompre le fonctionnement ou l'état stable ; une exception est donnée lorsque le fonctionnement et la stabilité dans le passage restent indépendants de leur état. Les portes admissibles aux records doivent fonctionner dans l'Overworld et obtenir au moins l'un des titres SEAMLESS.

Cette dernière exigence porte sur l'admissibilité aux records (section 3), tandis que les restrictions de placement sont décrites comme optionnelles dans la catégorisation (section 2.1.4). Le validateur alpha doit expliciter son périmètre entre définition de regular DOOR et admissibilité complète aux records.

Section 2.1.4 : SEAMLESS signifie que le circuit n'est pas visible dans le passage, avec une composition correspondant au type de porte. La table distingue SUPER, FULL, SEMI et QUART SEAMLESS par les états/opérations concernés. Le niveau QUART impose seulement l'absence de circuit visible sur la face avant des blocs de porte fermée ; les niveaux supérieurs étendent les exigences aux états ouvert/fermé et aux mouvements. L'interprétation exacte des blocs composant le circuit et de la visibilité doit s'appuyer sur les définitions du document, pas sur un rendu d'image seul.

## Volume (section 4.2)

Le volume est le produit largeur × hauteur × profondeur du circuit, avec dimensions arrondies à l'entier supérieur et cumulées sur les états ouverts/fermés et les mouvements. Les blocs et les entités peuvent contribuer à la mesure. Le cadre et le dispositif d'entrée sont exclus ; la source définit aussi des exclusions pour le passage et certaines parties d'entités, à transcrire précisément avant implémentation.

Lecture complémentaire de la section 4.2 le 8 octobre 2026 : les exceptions excluent le cadre de porte et le dispositif d'entrée. Les blocs ou entités situés dans le passage sont exclus sauf dans l'état ouvert. Deux exceptions supplémentaires concernent les entités : celles qui n'ont pas besoin de dépasser le circuit pour fonctionner, et certaines portions de hitbox à position flottante permettant encore la pose manuelle d'un bloc. Ces deux dernières exceptions ne concernent pas les constructions sans entités retenues pour l'alpha. L'illustration confirme une enveloppe cumulée des emplacements occupés pendant les opérations, plutôt que la plus grande des seules enveloppes ouverte et fermée.

## Vitesse (section 4.3.1)

La mesure se fait en temps du jeu ; le référentiel utilise 20 game ticks par seconde, avec une entrée par répéteur pour le chronométrage. Il distingue, par ordre de priorité, le temps d'ouverture, le temps d'ouverture visible, le temps de fermeture, le temps de fermeture visible, puis les délais de réactivation après ouverture et fermeture. Atteindre le motif ouvert et finir tous les mouvements du circuit sont des événements distincts.

## Lecture encore nécessaire

L'[illustration de REGULAR](https://imgur.com/a/3mj0xbW) a été consultée dans le navigateur : l'album « Regular (front views) » montre des rectangles pleins fermés, de face, en 2×2, 3×3 et 4×4. Ces vues de face ne suffisent pas à établir seules les détails de profondeur à retenir dans le validateur.

La section 2.2 définit `CONTINUABLE` par la possibilité de prolonger indéfiniment le motif du passage au-delà du circuit. Cette propriété est exigée par la définition des portes à pistons en 2.1.

Le lien Mojang [MC-172213](https://bugs.mojang.com/browse/MC-172213), donné pour distinguer entrée joueur et entrée par répéteur, a été ouvert mais son contenu n'a pas pu être lu par l'outil web. Les définitions opérationnelles de ces entrées et les exceptions de mesure doivent encore être vérifiées avant de spécifier le validateur.
