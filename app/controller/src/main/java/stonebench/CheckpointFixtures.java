package stonebench;

import net.minecraft.block.*;
import net.minecraft.block.entity.ChestBlockEntity;
import net.minecraft.block.enums.BlockFace;
import net.minecraft.item.*;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.state.property.Properties;
import net.minecraft.util.math.*;

/** Immutable prototype #3 geometry. Never relaxes the production lateral input API. */
final class CheckpointFixtures {
    private static final BlockPos LEVER=new BlockPos(1,80,1);
    private static void requireTest() {if(!Controller.TEST) throw new IllegalArgumentException("Test fixture unavailable on production server");}
    static void prepare(ServerWorld world) {
        requireTest();
        for(BlockPos pos:BlockPos.iterate(0,79,0,9,82,5)) {Observation.track(pos);world.setBlockState(pos,Blocks.AIR.getDefaultState(),Block.NOTIFY_ALL);}
        for(BlockPos pos:BlockPos.iterate(0,79,0,9,79,5)) world.setBlockState(pos,Blocks.STONE.getDefaultState(),Block.NOTIFY_ALL);
        world.setBlockState(LEVER,Blocks.LEVER.getDefaultState().with(Properties.BLOCK_FACE,BlockFace.FLOOR).with(Properties.HORIZONTAL_FACING,Direction.EAST),Block.NOTIFY_ALL);
        world.setBlockState(new BlockPos(2,80,1),Blocks.REPEATER.getDefaultState().with(Properties.HORIZONTAL_FACING,Direction.WEST).with(Properties.DELAY,2),Block.NOTIFY_ALL);
        world.setBlockState(new BlockPos(3,80,1),Blocks.STICKY_PISTON.getDefaultState().with(Properties.FACING,Direction.EAST),Block.NOTIFY_ALL);
        world.setBlockState(new BlockPos(4,80,1),Blocks.STONE.getDefaultState(),Block.NOTIFY_ALL);
        BlockPos chestPosition=new BlockPos(7,80,3);world.setBlockState(chestPosition,Blocks.CHEST.getDefaultState(),Block.NOTIFY_ALL);
        ChestBlockEntity chest=(ChestBlockEntity)world.getBlockEntity(chestPosition);
        chest.setStack(0,new ItemStack(Items.DIAMOND,7));chest.markDirty();
    }
    static void toggle(ServerWorld world) {
        requireTest();BlockState state=world.getBlockState(LEVER);
        if(!(state.getBlock() instanceof LeverBlock lever)) throw new IllegalArgumentException("Checkpoint fixture lever is missing");
        lever.togglePower(state,world,LEVER,null);
    }
}
