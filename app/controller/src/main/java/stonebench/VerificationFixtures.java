package stonebench;

import com.google.gson.JsonObject;
import net.minecraft.block.Block;
import net.minecraft.block.Blocks;
import net.minecraft.block.entity.ChestBlockEntity;
import net.minecraft.component.ComponentMap;
import net.minecraft.component.DataComponentTypes;
import net.minecraft.item.ItemStack;
import net.minecraft.item.Items;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.state.property.Properties;
import net.minecraft.util.math.BlockPos;
import net.minecraft.util.math.Direction;
import net.minecraft.block.enums.BlockFace;
import net.minecraft.text.Text;
import java.util.Set;

/** Test-only vanilla regular-door construction for exercising checkpoint verification. */
final class VerificationFixtures {
    private static final int Y=80, Z=1024;
    private static final BlockPos CONTROL_CHEST=new BlockPos(1032,80,1028);
    private static final BlockPos CONTROL_BLOCK=new BlockPos(1033,80,1028);

    private VerificationFixtures() {}

    static JsonObject prepare(ServerWorld world,String scenario) {
        if(!Controller.TEST) throw new IllegalArgumentException("Verification fixture unavailable on production server");
        if(!scenario.equals("door") && !scenario.equals("powered") && !scenario.equals("positive") && !scenario.equals("cycle1"))
            throw new IllegalArgumentException("Unknown verification fixture scenario: "+scenario);


        // Clear the complete door, lateral input and behind-frame wiring footprint.
        for(BlockPos pos:BlockPos.iterate(1016,78,1022,1029,83,1025)) put(world,pos,Blocks.AIR.getDefaultState());

        // Fixed 2x2 frame. The two quartz columns start outside the passage; four
        // real sticky pistons push them inward when the idle redstone bus is powered.
        for(int x=1023;x<=1026;x++) {
            put(world,new BlockPos(x,79,Z),Blocks.QUARTZ_BLOCK.getDefaultState());
            put(world,new BlockPos(x,82,Z),Blocks.QUARTZ_BLOCK.getDefaultState());
        }
        for(int y=Y;y<=81;y++) {
            put(world,new BlockPos(1022,y,Z),Blocks.STICKY_PISTON.getDefaultState().with(Properties.FACING,Direction.EAST));
            put(world,new BlockPos(1023,y,Z),Blocks.QUARTZ_BLOCK.getDefaultState());
            put(world,new BlockPos(1026,y,Z),Blocks.QUARTZ_BLOCK.getDefaultState());
            put(world,new BlockPos(1027,y,Z),Blocks.STICKY_PISTON.getDefaultState().with(Properties.FACING,Direction.WEST));
        }
        put(world,new BlockPos(1022,79,Z),Blocks.STONE.getDefaultState());
        put(world,new BlockPos(1027,79,Z),Blocks.STONE.getDefaultState());

        // A direct supported west-side lever feeds the four vanilla pistons.
        // Setup is open/inactive; the harness establishes closed/active state0
        // through a traced vanilla interaction before creating its checkpoint.
        put(world,new BlockPos(1018,80,Z),Blocks.STONE.getDefaultState());
        put(world,new BlockPos(1018,81,Z),Blocks.STONE.getDefaultState());
        put(world,new BlockPos(1017,81,Z),Blocks.LEVER.getDefaultState()
                .with(Properties.BLOCK_FACE,BlockFace.WALL)
                .with(Properties.HORIZONTAL_FACING,Direction.WEST));
        int[][] wire={{1019,81,1024},{1020,81,1024},{1020,81,1023},{1020,81,1022},
                      {1021,81,1022},{1022,81,1022},{1022,81,1023},
                      {1023,82,1022},{1024,83,1022},{1025,83,1022},
                      {1026,83,1022},{1027,83,1022},{1028,82,1022}};
        for(int[] cell:wire) put(world,new BlockPos(cell[0],cell[1]-1,cell[2]),Blocks.STONE.getDefaultState());
        for(int[] cell:wire) put(world,new BlockPos(cell[0],cell[1],cell[2]),Blocks.REDSTONE_WIRE.getDefaultState());
        put(world,new BlockPos(1025,83,1022),Blocks.REPEATER.getDefaultState().with(Properties.HORIZONTAL_FACING,Direction.WEST));
        // Full stationary supports power the upper right side and lower rear.
        put(world,new BlockPos(1028,81,Z-1),Blocks.STONE.getDefaultState());
        put(world,new BlockPos(1028,81,Z),Blocks.STONE.getDefaultState());
        put(world,new BlockPos(1028,82,Z-1),Blocks.REDSTONE_WIRE.getDefaultState());
        put(world,new BlockPos(1028,82,Z),Blocks.REDSTONE_WIRE.getDefaultState());
        int[][] lower={{1029,82,1022},{1029,81,1023},{1029,81,1024},
                       {1029,81,1025},{1028,81,1025},{1027,81,1025}};
        for(int[] cell:lower) put(world,new BlockPos(cell[0],cell[1]-1,cell[2]),Blocks.STONE.getDefaultState());
        for(int[] cell:lower) put(world,new BlockPos(cell[0],cell[1],cell[2]),Blocks.REDSTONE_WIRE.getDefaultState());

        // Exact comparison controls live away from both continuation rays.
        put(world,new BlockPos(1032,79,1028),Blocks.STONE.getDefaultState());
        put(world,CONTROL_CHEST,Blocks.CHEST.getDefaultState());
        ChestBlockEntity chest=(ChestBlockEntity)world.getBlockEntity(CONTROL_CHEST);
        chest.setStack(0,new ItemStack(Items.DIAMOND,7));
        setChestName(chest,"verification-marker");
        chest.markDirty();
        put(world,CONTROL_BLOCK,Blocks.STONE.getDefaultState());

        JsonObject declaration=new JsonObject();
        declaration.addProperty("device","minecraft:lever");
        declaration.add("position",Task.position(1017,81,Z));
        declaration.addProperty("orientation","west");
        declaration.add("input_block",Task.position(1018,81,Z));
        declaration.addProperty("fixture_mode","powered");
        declaration.addProperty("active_at_setup",false);
        return declaration;
    }

    /** Controlled state divergence applied only after a real worker transition. */
    static JsonObject mutate(ServerWorld world,String scenario,int cycle,String mode,String boundary) {
        if(!Controller.TEST) throw new IllegalArgumentException("Verification mutation unavailable on production server");
        if(!Set.of("repeater","direct").contains(mode) || !Set.of("open","closed").contains(boundary) || cycle<1 || cycle>5)
            throw new IllegalArgumentException("Invalid verification mutation boundary");
        JsonObject result=new JsonObject();
        result.addProperty("scenario",scenario);result.addProperty("mode",mode);result.addProperty("cycle",cycle);result.addProperty("boundary",boundary);
        if(scenario.equals("positive") || scenario.equals("none")) {result.addProperty("mutated",false);return result;}
        boolean closed=boundary.equals("closed");
        if(scenario.equals("recurrence2") && closed && (mode.equals("repeater") || cycle==1)) {
            setDiamondCount(world,mode.equals("direct")?8:cycle==1?8:7);result.addProperty("mutated",true);
        } else if(scenario.equals("no_return5") && closed && (mode.equals("repeater") || cycle==1)) {
            setDiamondCount(world,7+cycle);result.addProperty("mutated",true);
        } else if(scenario.equals("direct_block") && mode.equals("direct") && closed) {
            put(world,CONTROL_BLOCK,Blocks.GOLD_BLOCK.getDefaultState());result.addProperty("mutated",true);
        } else if(scenario.equals("direct_inventory") && mode.equals("direct") && closed) {
            setDiamondCount(world,8);result.addProperty("mutated",true);
        } else if(scenario.equals("direct_internal") && mode.equals("direct") && closed) {
            ChestBlockEntity chest=chest(world);setChestName(chest,"verification-marker-changed");chest.markDirty();result.addProperty("mutated",true);
        } else if(scenario.equals("bad_open") && mode.equals("repeater") && cycle==1 && boundary.equals("open")) {
            put(world,new BlockPos(1024,80,Z),Blocks.STONE.getDefaultState());result.addProperty("mutated",true);
        } else if(scenario.equals("positive") || scenario.equals("none") || Set.of("recurrence2","no_return5","direct_block","direct_inventory","direct_internal","bad_open").contains(scenario)) {
            result.addProperty("mutated",false);
        } else throw new IllegalArgumentException("Unknown verification mutation scenario: "+scenario);
        return result;
    }

    private static ChestBlockEntity chest(ServerWorld world) {
        Observation.track(CONTROL_CHEST);
        if(!(world.getBlockEntity(CONTROL_CHEST) instanceof ChestBlockEntity chest))
            throw new IllegalStateException("Verification comparison chest is missing");
        return chest;
    }

    private static void setDiamondCount(ServerWorld world,int count) {
        ChestBlockEntity chest=chest(world);
        chest.setStack(0,new ItemStack(Items.DIAMOND,count));chest.markDirty();
    }

    private static void setChestName(ChestBlockEntity chest,String name) {
        ComponentMap components=ComponentMap.builder().addAll(chest.getComponents())
                .add(DataComponentTypes.CUSTOM_NAME,Text.literal(name)).build();
        chest.setComponents(components);
    }

    private static void put(ServerWorld world,BlockPos pos,net.minecraft.block.BlockState state) {
        Observation.track(pos);
        world.setBlockState(pos,state,Block.NOTIFY_ALL);
    }
}
