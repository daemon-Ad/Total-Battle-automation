import time
import json
import os
import random
from crypting.crypter import Crypter

def generate_chunks(total_target, min_chunks=3, max_per_chunk=6):
    """
    Splits the total target into randomized chunks.
    Ensures at least min_chunks are generated and no chunk exceeds max_per_chunk.
    """
    if total_target <= 0:
        return []
        
    chunks = []
    remaining = total_target
    
    while remaining > 0:
        needed_future_chunks = max(0, min_chunks - len(chunks) - 1)
        safe_max = remaining - needed_future_chunks
        upper_bound = min(safe_max, max_per_chunk)
        
        if upper_bound < 1:
            chunk_size = remaining
        else:
            chunk_size = random.randint(1, upper_bound)
            
        chunks.append(chunk_size)
        remaining -= chunk_size
        
    # Shuffle chunks to randomize the execution order
    random.shuffle(chunks)
    return chunks

def main():
    print("Initializing Total Battle Orchestrator...")
    config_path = "config/moto-g51-config.json"
    
    if not os.path.exists(config_path):
        print("Config file not found. Ensure moto-g51-config.json exists.")
        return
        
    with open(config_path, "r") as f:
        config = json.load(f)
        
    daily_target = config.get("daily_crypt_target", 15)
    print(f"Daily Crypt Target loaded: {daily_target}")
    
    chunks = generate_chunks(daily_target, min_chunks=3, max_per_chunk=6)
    print(f"Orchestration Plan: Executing in {len(chunks)} chunks -> {chunks}")
    
    crypter = Crypter("moto-g51")
    
    for i, chunk_size in enumerate(chunks):
        print(f"\n=======================================================")
        print(f"Orchestrator Run {i+1}/{len(chunks)}: Starting chunk of {chunk_size} crypts.")
        print(f"=======================================================")
        
        crypter.run_loop(chunk_size)
        
        if i < len(chunks) - 1:
            # Sleep 2 to 6 minutes between runs
            deep_sleep_seconds = random.uniform(120, 360)
            print(f"\nChunk complete. Orchestrator entering deep sleep for {deep_sleep_seconds/60:.1f} minutes...")
            time.sleep(deep_sleep_seconds)
            print("Waking up for next chunk...")
            
    print("\nOrchestrator finished daily target!")

if __name__ == "__main__":
    main()
