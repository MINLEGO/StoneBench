package stonebench;

import com.google.gson.*;
import java.util.*;
import net.minecraft.block.*;
import net.minecraft.block.piston.PistonBehavior;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.util.math.*;

/** Snapshot diagnostics, not a replacement for the functional protocol or rest detection. */
public final class RegularDoorGeometry {
    record Cell(int x,int y,int z,String block,boolean collision,boolean fullCube,boolean quartzCandidate,boolean enclosureFace) {
        Cell(int x,int y,int z,String block,boolean collision,boolean fullCube,boolean quartzCandidate){this(x,y,z,block,collision,fullCube,quartzCandidate,fullCube);}
        String key(){return x+","+y+","+z;}
        JsonObject json(){JsonObject p=Task.position(x,y,z);p.addProperty("block",block);p.addProperty("collision",collision);p.addProperty("full_cube",fullCube);p.addProperty("quartz_candidate",quartzCandidate);return p;}
    }
    record Frame(int x,int y,int z,int width,int height,int minZ,int maxZ,String expected) {
        boolean interior(Cell p){return p.x>=x&&p.x<x+width&&p.y>=y&&p.y<y+height;}
        boolean layer(Cell p){return p.z>=minZ&&p.z<=maxZ;}
        boolean ring(Cell p){return layer(p)&&p.x>=x-1&&p.x<=x+width&&p.y>=y-1&&p.y<=y+height&&!interior(p)&&((p.x>=x&&p.x<x+width)||(p.y>=y&&p.y<y+height));}
    }
    static Frame frame(JsonObject task,JsonObject args) {
        if(!Set.of("expected_state","frame_min_z","frame_max_z").containsAll(args.keySet())) throw new IllegalArgumentException("Unexpected geometry argument; arbitrary exclusions/shifted passage are forbidden");
        String expected=Task.string(args,"expected_state");if(!Set.of("open","closed").contains(expected)) throw new IllegalArgumentException("expected_state must be open or closed");
        JsonObject origin=task.getAsJsonObject("passage").getAsJsonObject("origin");int z=origin.get("z").getAsInt();
        if(args.has("frame_min_z")!=args.has("frame_max_z")) throw new IllegalArgumentException("Supply both frame_min_z and frame_max_z");
        int min=args.has("frame_min_z")?Task.integer(args,"frame_min_z",-30000000,30000000):z,max=args.has("frame_max_z")?Task.integer(args,"frame_max_z",-30000000,30000000):z;
        if(min>z||max<z||max-min>255) throw new IllegalArgumentException("Frame layers must contain the immutable passage plane and span at most 256 layers; split larger diagnostics explicitly");
        return new Frame(origin.get("x").getAsInt(),origin.get("y").getAsInt(),z,task.get("width").getAsInt(),task.get("height").getAsInt(),min,max,expected);
    }
    public static List<BlockPos> requiredPositions(JsonObject task,JsonObject args) {
        Frame f=frame(task,args);List<BlockPos> p=new ArrayList<>();for(int z=f.minZ;z<=f.maxZ;z++)for(int y=f.y-1;y<=f.y+f.height;y++)for(int x=f.x-1;x<=f.x+f.width;x++)p.add(new BlockPos(x,y,z));return p;
    }
    /** Controller must prepare requiredPositions before calling; this adds no simulation tick. */
    public static JsonObject check(ServerWorld world,JsonObject task,JsonObject args,JsonObject input) {
        for(BlockPos p:requiredPositions(task,args)) {if(!Controller.prepared(p)) throw new IllegalStateException("Geometry requires prepared chunks");Observation.track(p);}
        Frame frame=frame(task,args);JsonObject raw=Observation.raw(world);List<Cell> cells=new ArrayList<>();Set<String> adapters=new HashSet<>();
        if(input!=null&&input.has("adapter_positions"))for(JsonElement p:input.getAsJsonArray("adapter_positions")) {JsonObject q=p.getAsJsonObject();adapters.add(q.get("x")+","+q.get("y")+","+q.get("z"));}
        int minX=Integer.MAX_VALUE,minY=Integer.MAX_VALUE,minZ=Integer.MAX_VALUE,maxX=Integer.MIN_VALUE,maxY=Integer.MIN_VALUE,maxZ=Integer.MIN_VALUE;
        for(JsonElement value:raw.getAsJsonObject("blocks").asMap().values()) {
            JsonObject row=value.getAsJsonObject();int x=row.get("x").getAsInt(),y=row.get("y").getAsInt(),z=row.get("z").getAsInt();BlockPos p=new BlockPos(x,y,z);if(adapters.contains(x+","+y+","+z))continue;
            BlockState s=world.getBlockState(p);boolean candidate=s.isOpaqueFullCube()&&s.getPistonBehavior()==PistonBehavior.NORMAL&&!(s.getBlock() instanceof FallingBlock);
            Direction inward=x<frame.x?Direction.EAST:x>=frame.x+frame.width?Direction.WEST:y<frame.y?Direction.UP:Direction.DOWN;
            cells.add(new Cell(x,y,z,row.get("block").getAsString(),!s.getCollisionShape(world,p).isEmpty(),s.isFullCube(world,p),candidate,Block.isFaceFullSquare(s.getCollisionShape(world,p),inward)));
            minX=Math.min(x,minX);minY=Math.min(y,minY);minZ=Math.min(z,minZ);maxX=Math.max(x,maxX);maxY=Math.max(y,maxY);maxZ=Math.max(z,maxZ);
        }
        JsonArray entities=new JsonArray();if(!cells.isEmpty())for(var e:world.getOtherEntities(null,new Box(minX,minY,minZ,maxX+1,maxY+1,maxZ+1))) {JsonObject row=new JsonObject();row.addProperty("uuid",e.getUuidAsString());row.addProperty("type",net.minecraft.registry.Registries.ENTITY_TYPE.getId(e.getType()).toString());entities.add(row);}
        JsonObject liveInput=input==null?null:input.deepCopy();
        if(liveInput!=null) {
            JsonObject device=liveInput.getAsJsonObject("driver"),support=liveInput.getAsJsonObject("input_block");
            BlockPos dp=new BlockPos(device.get("x").getAsInt(),device.get("y").getAsInt(),device.get("z").getAsInt()),ip=new BlockPos(support.get("x").getAsInt(),support.get("y").getAsInt(),support.get("z").getAsInt());
            BlockState ds=world.getBlockState(dp);Direction outward=Direction.byId(liveInput.get("orientation").getAsString());
            boolean valid=outward!=null&&outward.getAxis().isHorizontal()&&net.minecraft.registry.Registries.BLOCK.getId(ds.getBlock()).toString().equals(liveInput.get("device").getAsString())&&ds.contains(net.minecraft.state.property.Properties.BLOCK_FACE)&&ds.get(net.minecraft.state.property.Properties.BLOCK_FACE)==net.minecraft.block.enums.BlockFace.WALL&&ds.get(net.minecraft.state.property.Properties.HORIZONTAL_FACING)==outward&&ds.canPlaceAt(world,dp)&&!world.getBlockState(ip).isAir();
            if(valid)for(Cell c:cells)if(!c.block.equals("minecraft:air")) {int delta=outward.getAxis()==Direction.Axis.X?c.x-ip.getX():c.z-ip.getZ();if(delta*outward.getDirection().offset()>0){valid=false;break;}}
            if(!valid)liveInput.addProperty("validation","live_device_support_or_exterior_invalid");
        }
        JsonObject report=evaluate(task,args,cells,raw.getAsJsonObject("coverage"),liveInput,entities);report.addProperty("world_time",world.getTime());report.addProperty("frozen_snapshot",true);return report;
    }
    static JsonObject evaluate(JsonObject task,JsonObject args,List<Cell> cells,JsonObject coverage,JsonObject input,JsonArray entities) {
        Frame f=frame(task,args);Map<String,Cell> byPosition=new HashMap<>();for(Cell c:cells)byPosition.put(c.key(),c);
        boolean complete=coverage.has("status")&&coverage.get("status").getAsString().equals("observed")&&coverage.has("chunks_ready")&&coverage.get("chunks_ready").getAsBoolean();
        JsonArray frameRows=new JsonArray(),missing=new JsonArray(),invalidComposition=new JsonArray(),unknownComposition=new JsonArray(),ringMissing=new JsonArray(),ringUnusual=new JsonArray(),obstructions=new JsonArray(),exclusions=new JsonArray();boolean frameComplete=true;
        for(int z=f.minZ;z<=f.maxZ;z++)for(int y=f.y-1;y<=f.y+f.height;y++)for(int x=f.x-1;x<=f.x+f.width;x++) {
            Cell c=byPosition.get(x+","+y+","+z);if(c==null){frameComplete=false;missing.add(Task.position(x,y,z));continue;}
            if(f.interior(c)) {
                frameRows.add(c.json());if(f.expected.equals("open")?c.collision:!c.fullCube)missing.add(c.json());
                if(f.expected.equals("closed")) {if(!c.quartzCandidate)invalidComposition.add(c.json());else if(!c.block.equals("minecraft:quartz_block"))unknownComposition.add(c.json());}
                JsonObject role=c.json();role.addProperty("role","frame_interior");role.addProperty("volume_exclusion",f.expected.equals("closed")?"hallway_nonopen":"conditional_open_pattern");exclusions.add(role);
            } else if(f.ring(c)) {
                if(!c.collision)ringMissing.add(c.json());else if(!c.enclosureFace)ringUnusual.add(c.json());
                JsonObject role=c.json();role.addProperty("role","physical_encadrement");role.addProperty("volume_exclusion",c.block.equals("minecraft:piston_head")||c.block.equals("minecraft:moving_piston")?"retained_wiring":"conditional_frame_or_hallway_role; never arbitrary circuit exclusion");exclusions.add(role);
            }
        }
        for(Cell c:cells)if(f.interior(c)&&!f.layer(c)&&c.collision)obstructions.add(c.json());
        JsonArray rows=new JsonArray();
        add(rows,"fixed_passage","satisfied",task.get("passage"),"Frame layers anchored to immutable passage, independent of physical construction.");
        String normal=task.getAsJsonObject("passage").get("normal").getAsString();boolean cardinal=Set.of("+Z","-Z","+X","-X").contains(normal);
        add(rows,"door_orientation",cardinal?"satisfied":"failed",new JsonPrimitive(normal),"DOOR cardinal orientation; skydoor is outside alpha.");
        add(rows,"regular_arrangement",!normal.equals("+Z")?"indeterminate":frameComplete?"satisfied":"indeterminate",frameRows,"Rectangular task cross-section and declared frame layers; +Z task basis implemented. Depth is declared explicitly, not prescribed by an image.");
        add(rows,"frame_state",!frameComplete?"indeterminate":missing.isEmpty()?"satisfied":"failed",missing,"Snapshot occupancy/collision pattern; this does not establish a stable state.");
        add(rows,"door_composition",f.expected.equals("open")?"not_verified":!frameComplete?"indeterminate":!invalidComposition.isEmpty()?"failed":!unknownComposition.isEmpty()?"indeterminate":"satisfied",!invalidComposition.isEmpty()?invalidComposition:unknownComposition,"Quartz identity substitution is conclusive; opaque movable nongravity alternatives require behavioral substitution proof. Open geometry cannot infer closed door material.");
        add(rows,"encadrement",!frameComplete?"indeterminate":!ringMissing.isEmpty()?"failed":!ringUnusual.isEmpty()?"indeterminate":"satisfied",!ringMissing.isEmpty()?ringMissing:ringUnusual,"Physical perimeter at fixed passage; collision faces covering the inward wall/floor/ceiling side prove enclosure. Unusual partial shapes are not forbidden, but need traversal evidence.");
        add(rows,"continuable",!obstructions.isEmpty()?"failed":!complete?"indeterminate":"satisfied",obstructions,"No observed obstruction on fixed passage rays beyond frame layers; tracked static wiring region permits indefinite continuation beyond its extents. Transient completeness assessed separately.");
        add(rows,"hallway_composition","not_verified",JsonNull.INSTANCE,"Optional quartz/air composition outside SUPER/FULL SEAMLESS; no strict air-id or wall-material requirement.");
        boolean inputValid=input!=null&&input.has("validation")&&input.get("validation").getAsString().equals("validated_lateral_exterior")&&input.has("face")&&input.get("face").getAsString().equals("wall");
        add(rows,"input",input==null?"indeterminate":inputValid?"satisfied":"failed",input==null?JsonNull.INSTANCE:input,"Live declaration is read from Inputs, never accepted as caller-supplied evidence; top/bottom placement is invalid.");
        add(rows,"no_entities",entities.isEmpty()?"satisfied":"failed",entities,"Entities within tracked construction bounds; absence is not a universal influence certificate.");
        add(rows,"no_required_clock","indeterminate",JsonNull.INSTANCE,"Requires operational transition proof; no component blacklist or frozen-state inference.");
        add(rows,"stable_state","indeterminate",JsonNull.INSTANCE,"This tool observes a snapshot; bounded transition/rest protocol supplies stability evidence.");
        add(rows,"influence_coverage","indeterminate",coverage,"Insufficient/gapped coverage blocks certification. Even a complete static snapshot does not establish all temporal influences and transient positions; protocol must supply that evidence.");
        for(String id:List.of("record_reliability","record_isolation","record_seamless"))add(rows,id,"not_verified",JsonNull.INSTANCE,"Community record rule outside alpha coverage.");
        if(input!=null&&input.has("input_block")) {
            JsonObject support=input.getAsJsonObject("input_block");boolean found=false;
            for(JsonElement e:exclusions){JsonObject r=e.getAsJsonObject();if(samePosition(r,support)){r.addProperty("role","input_block");r.addProperty("volume_exclusion","retained_wiring");found=true;}}
            if(!found){JsonObject r=support.deepCopy();r.addProperty("role","input_block");r.addProperty("volume_exclusion","retained_wiring");exclusions.add(r);}
            if(input.has("adapter_positions"))for(JsonElement e:input.getAsJsonArray("adapter_positions")){JsonObject r=e.getAsJsonObject().deepCopy();r.addProperty("role",input.has("driver")&&samePosition(r,input.getAsJsonObject("driver"))?"input_device":"external_adapter");r.addProperty("volume_exclusion","excluded_validated_input_adapter");exclusions.add(r);}
        }
        JsonObject report=new JsonObject();report.addProperty("protocol_version",Rules.VERSION);report.addProperty("expected_state",f.expected);report.addProperty("frame_min_z",f.minZ);report.addProperty("frame_max_z",f.maxZ);report.add("criteria",rows);report.add("measurement_roles",exclusions);report.add("coverage",coverage.deepCopy());
        boolean failed=false;for(JsonElement r:rows)if(r.getAsJsonObject().get("mandatory").getAsBoolean()&&r.getAsJsonObject().get("status").getAsString().equals("failed"))failed=true;
        report.addProperty("geometry_status",failed?"failed":"indeterminate");report.addProperty("conforms_to_alpha",false);report.addProperty("scope","Geometry snapshot diagnostics; functional protocol, stability and measurements are separate.");return report;
    }
    static boolean samePosition(JsonObject a,JsonObject b){return a.get("x").equals(b.get("x"))&&a.get("y").equals(b.get("y"))&&a.get("z").equals(b.get("z"));}
    private static java.util.UUID fixtureEntity;
    public static JsonObject testEntity(ServerWorld world,boolean present) {
        if(!Controller.TEST)throw new IllegalArgumentException("Test-only geometry fixture");
        if(fixtureEntity!=null){var e=world.getEntity(fixtureEntity);if(e!=null)e.discard();fixtureEntity=null;}
        if(present){var e=new net.minecraft.entity.ItemEntity(world,1024.5,80.5,1024.5,new net.minecraft.item.ItemStack(net.minecraft.item.Items.STONE));if(!world.spawnEntity(e))throw new IllegalStateException("Could not spawn fixture entity");fixtureEntity=e.getUuid();}
        JsonObject result=new JsonObject();result.addProperty("present",present);return result;
    }
    static void add(JsonArray rows,String id,String status,JsonElement observed,String detail){rows.add(Rules.diagnostic(id,status,observed,detail));}
}
