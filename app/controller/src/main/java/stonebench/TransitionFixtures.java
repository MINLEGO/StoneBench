package stonebench;

import com.google.gson.*;
import java.util.*;
import net.minecraft.block.*;
import net.minecraft.block.entity.*;
import net.minecraft.block.enums.BlockFace;
import net.minecraft.item.*;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.state.property.Properties;
import net.minecraft.util.math.*;
import stonebench.mixin.RestHopperFixtureAccess;

/** Disposable test-server fixtures from immutable prototype #1; never production tools. */
public final class TransitionFixtures {
    static final BlockPos LEVER=new BlockPos(1025,80,1025),HOPPER=new BlockPos(1027,80,1026),CHEST=new BlockPos(1028,80,1026);
    static void prepare(ServerWorld world,String scenario) {
        if(!Controller.TEST) throw new IllegalArgumentException("Unknown tool");
        if(!Set.of("piston","chain","hopper_cooldown","hopper_empty","hopper_locked","clock","clear").contains(scenario)) throw new IllegalArgumentException("Unknown transition fixture");
        for(BlockPos p:BlockPos.iterate(1024,79,1024,1033,82,1029)) {Observation.track(p);world.setBlockState(p,Blocks.AIR.getDefaultState(),Block.FORCE_STATE_AND_SKIP_CALLBACKS_AND_DROPS);}
        for(BlockPos p:BlockPos.iterate(1024,79,1024,1033,79,1029)) world.setBlockState(p,Blocks.STONE.getDefaultState(),Block.NOTIFY_ALL);
        if(scenario.equals("piston") || scenario.equals("chain")) {
            world.setBlockState(LEVER,Blocks.LEVER.getDefaultState().with(Properties.BLOCK_FACE,BlockFace.FLOOR).with(Properties.HORIZONTAL_FACING,Direction.EAST),Block.NOTIFY_ALL);
            int n=scenario.equals("chain")?3:1;
            for(int i=0;i<n;i++) world.setBlockState(new BlockPos(1026+i,80,1025),Blocks.REPEATER.getDefaultState().with(Properties.HORIZONTAL_FACING,Direction.WEST).with(Properties.DELAY,n==3?4:2),Block.NOTIFY_ALL);
            world.setBlockState(new BlockPos(1026+n,80,1025),Blocks.STICKY_PISTON.getDefaultState().with(Properties.FACING,Direction.EAST),Block.NOTIFY_ALL);
            world.setBlockState(new BlockPos(1027+n,80,1025),Blocks.STONE.getDefaultState(),Block.NOTIFY_ALL);
        } else if(scenario.startsWith("hopper")) {
            world.setBlockState(CHEST,Blocks.CHEST.getDefaultState(),Block.NOTIFY_ALL);
            world.setBlockState(HOPPER,Blocks.HOPPER.getDefaultState().with(HopperBlock.FACING,Direction.EAST),Block.NOTIFY_ALL);
            if(scenario.equals("hopper_locked")) world.setBlockState(new BlockPos(1026,80,1026),Blocks.REDSTONE_BLOCK.getDefaultState(),Block.NOTIFY_ALL);
            if(scenario.equals("hopper_cooldown")) {
                HopperBlockEntity hopper=(HopperBlockEntity)world.getBlockEntity(HOPPER);hopper.setStack(0,new ItemStack(Items.DIAMOND,3));((RestHopperFixtureAccess)hopper).stonebench$fixtureCooldown(8);hopper.markDirty();
            }
        } else if(scenario.equals("clock")) {
            world.setBlockState(new BlockPos(1026,80,1026),Blocks.OBSERVER.getDefaultState().with(Properties.FACING,Direction.EAST),Block.NOTIFY_ALL);
            world.setBlockState(new BlockPos(1027,80,1026),Blocks.OBSERVER.getDefaultState().with(Properties.FACING,Direction.WEST),Block.NOTIFY_ALL);
        }
    }
    static void toggle(ServerWorld world) {
        if(!Controller.TEST) throw new IllegalArgumentException("Unknown tool");
        BlockState state=world.getBlockState(LEVER);if(!(state.getBlock() instanceof LeverBlock lever)) throw new IllegalArgumentException("Fixture lever unavailable");
        lever.togglePower(state,world,LEVER,null);
    }
}


