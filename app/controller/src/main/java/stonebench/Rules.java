package stonebench;

import com.google.gson.*;
import java.util.*;

/** Paraphrased, versioned operational rules; source indexes are Google Docs character indexes. */
public final class Rules {
    public static final String VERSION="regular-door-alpha-2026-10-11";
    public static final String REVISION="AHj4eMT_keZ9k_mo9La-s7C1bFHDqp8qAcERIYP8JSNCf922quSNhQQ0ICk0WEgJCGqRKxiqzo8qUe4DNy7-4Q";
    record Criterion(String id,int index,String expected,String observation,String coverage,boolean mandatory) {}
    static final List<Criterion> CRITERIA=List.of(
        new Criterion("fixed_passage",1606,"Use the immutable task origin, width, height and cardinal normal; frame layers include its plane.","Task and declared frame layers","static",true),
        new Criterion("door_orientation",4480,"Frame faces a cardinal direction; skydoors are excluded by alpha.","Task normal","static",true),
        new Criterion("regular_arrangement",2336,"Rectangular regular arrangement with task width and height, measured inside frame; no universal depth inferred from the linked face image.","Declared layer(s) and rectangular occupancy","static; other regular shapes remain indeterminate",true),
        new Criterion("door_composition",2932,"Door blocks are quartz-like, including preserved functionality after quartz substitution.","Closed frame block properties; canonical quartz is identity substitution","static canonical quartz; non-quartz substitution needs behavioral evidence",true),
        new Criterion("frame_state",30358,"No door block inside the frame when open, all closed door blocks inside when closed.","Frame layer occupancy, independent of rest","static pattern only; stability separately required",true),
        new Criterion("encadrement",30166,"Physical walls, floor and ceiling enclose the fixed frame; they are distinct from the interior cross-section.","Perimeter collision of declared layer(s); Dummies index 9641","static inward collision faces; unusual shapes indeterminate",true),
        new Criterion("continuable",14017,"Fixed entrance pattern extends in either normal direction without colliding with wiring.","All observed blocks on passage rays, including positions outside declared layers; Dummies index 5274","snapshot plus temporal influence coverage required",true),
        new Criterion("hallway_composition",3627,"Quartz-like hallway and air defaults are optional for this alpha without SUPER/FULL SEAMLESS.","Collision and wiring assessed separately; no mandatory quartz wall or air-id whitelist","not an alpha restriction; source exception index 3852",false),
        new Criterion("input",19273,"A supported button or lever on a lateral exterior surface has constant support; input block remains wiring.","Validated live input declaration; alpha forbids top/bottom attachment","input tool integration",true),
        new Criterion("no_entities",567,"Alpha excludes constructions using entities.","Entities within observed construction bounds","presence fails conservatively; absence limited to tracked influence bounds",true),
        new Criterion("no_required_clock",20402,"Alpha excludes a permanently running internal clock required for operation.","Transition/rest behavior, not an invented component blacklist","transition proof required; snapshot cannot determine necessity",true),
        new Criterion("stable_state",30583,"The requested open/closed pattern is stable until the next input.","Transition/rest certificate","not inferred from a frozen snapshot",true),
        new Criterion("influence_coverage",30106,"All relevant influences and transient positions are observed without gaps.","Observation coverage and trace completeness","snapshot cannot prove temporal completeness",true),
        new Criterion("record_reliability",20096,"Community reliability over time and normal gameplay.","Not covered by bounded alpha cycles","outside alpha",false),
        new Criterion("record_isolation",21859,"Player movement and external activations do not break stable states.","Not covered by the alpha","outside alpha",false),
        new Criterion("record_seamless",22706,"Community record title requires a seamless tier.","No seamless restriction requested by alpha","outside alpha",false)
    );
    public static JsonObject describe() {
        JsonObject result=new JsonObject();result.addProperty("protocol_version",VERSION);result.addProperty("source",Task.RULES);result.addProperty("revision_id",REVISION);
        result.addProperty("native_cache_sha256","e4a01f6d47956291bb9952392e3cf8216f2dc3c4537a81aaea0ccaf73e44eb68");
        JsonArray rows=new JsonArray();for(Criterion c:CRITERIA) rows.add(row(c));result.add("criteria",rows);
        JsonObject measures=new JsonObject();
        measures.addProperty("volume_source_index",23868);measures.addProperty("volume","Union of wiring extents through every open/closed state and movement; ceil each dimension, multiply; not block count or endpoint maximum.");
        measures.addProperty("exclusions_source_indexes","24437,24616,24688,24918,30714");
        measures.addProperty("exclusions","Frame and input device excluded; input block retained as wiring. Door/outer-surface/hallway composition exclusions are conditional on the required open pattern. Hallway contents excluded except when open. Entity exclusions are outside alpha; no arbitrary supplied exclusion list.");
        measures.addProperty("timing_source_indexes","26513,26906,26998,27066,27128,27683,28244");
        measures.addProperty("timing_origin","Input interaction in repeater mode; retain signal-at-input-block timestamp separately.");
        measures.addProperty("opening_end","End of last movement establishing the required opened arrangement/composition in the hallway.");
        measures.addProperty("closing_end","End of last door-block movement during closing.");
        measures.addProperty("movement_end","Standard extension/retraction: start+2gt; instant retraction: start; 0..2gt pulse extension: start+pulse length.");
        measures.addProperty("rest","Rest recognition is distinct; no dynamic volume or timing measurement in geometry checks.");result.add("measurement_contract",measures);return result;
    }
    static JsonObject row(Criterion c) {
        JsonObject row=new JsonObject();row.addProperty("id",c.id);row.addProperty("source",Task.RULES);row.addProperty("source_index",c.index);row.addProperty("revision_id",REVISION);row.addProperty("expected",c.expected);row.addProperty("observation",c.observation);row.addProperty("coverage",c.coverage);row.addProperty("mandatory",c.mandatory);return row;
    }
    static JsonObject diagnostic(String id,String status,JsonElement observed,String detail) {
        Criterion c=CRITERIA.stream().filter(v->v.id.equals(id)).findFirst().orElseThrow();JsonObject row=row(c);row.addProperty("status",status);row.add("observed",observed);row.addProperty("diagnostic",detail);return row;
    }
}

