#!/usr/bin/env python3
"""
Test script for PolyVector module
Tests both file-based and numpy array-based vectorization
"""

import sys
import time
from pathlib import Path

def test_import():
    """Test if module can be imported"""
    print("Testing module import...")
    try:
        import gp_linevector
        print(f"✓ Successfully imported gp_linevector v{gp_linevector.__version__}")
        return gp_linevector
    except ImportError as e:
        print(f"✗ Failed to import gp_linevector: {e}")
        print("\nMake sure to build and install the wheel first:")
        print("  python setup_vectorize.py bdist_wheel")
        print("  pip install dist/gp_linevector-*.whl")
        sys.exit(1)

def test_with_numpy_array():
    """Test vectorization with numpy array"""
    print("\nTesting with numpy array...")
    try:
        import numpy as np
        import gp_linevector
        
        # Create a simple test image (cross pattern)
        img = np.ones((100, 100), dtype=np.uint8) * 255  # White background
        
        # Draw black cross
        img[45:55, :] = 0  # Horizontal line
        img[:, 45:55] = 0  # Vertical line
        
        print("  Image shape:", img.shape)
        print("  Vectorizing...")
        
        start_time = time.time()
        strokes = gp_linevector.vectorize_array(img, threshold=128)
        elapsed = time.time() - start_time
        
        print(f"  ✓ Vectorization complete in {elapsed:.2f}s")
        print(f"  Found {len(strokes)} strokes")
        
        if len(strokes) > 0:
            for i, stroke in enumerate(strokes[:3]):  # Show first 3
                print(f"    Stroke {i}: {len(stroke)} points")
        
        return True
        
    except Exception as e:
        print(f"  ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_with_image_file():
    """Test vectorization with image file"""
    print("\nTesting with image file...")
    
    # Check if sample image exists
    sample_dir = Path("Vectorize/PolyVectorization/sample_inputs")
    if not sample_dir.exists():
        print("  ⚠ Sample images not found, skipping file test")
        return True
    
    sample_images = list(sample_dir.glob("*.png"))
    if not sample_images:
        print("  ⚠ No PNG files found in sample_inputs, skipping file test")
        return True
    
    test_image = sample_images[0]
    print(f"  Testing with: {test_image.name}")
    
    try:
        import gp_linevector
        
        start_time = time.time()
        strokes = gp_linevector.vectorize_image(str(test_image), threshold=90)
        elapsed = time.time() - start_time
        
        print(f"  ✓ Vectorization complete in {elapsed:.2f}s")
        print(f"  Found {len(strokes)} strokes")
        
        if len(strokes) > 0:
            total_points = sum(len(s) for s in strokes)
            print(f"    Total points: {total_points}")
            print(f"    Average points per stroke: {total_points / len(strokes):.1f}")
        
        return True
        
    except Exception as e:
        print(f"  ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_performance():
    """Test performance with different image sizes"""
    print("\nTesting performance...")
    try:
        import numpy as np
        import gp_linevector
        
        sizes = [(50, 50), (100, 100), (200, 200)]
        
        for size in sizes:
            img = np.ones(size, dtype=np.uint8) * 255
            # Simple pattern
            img[size[0]//3:2*size[0]//3, :] = 0
            
            start_time = time.time()
            strokes = gp_linevector.vectorize_array(img, threshold=128)
            elapsed = time.time() - start_time
            
            print(f"  {size[0]}x{size[1]}: {elapsed:.3f}s ({len(strokes)} strokes)")
        
        return True
        
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False

def main():
    print("=" * 50)
    print("GP LineVector Module Test Suite")
    print("=" * 50)
    
    # Test import
    gp_linevector = test_import()
    
    # Run tests
    tests = [
        ("Numpy Array Test", test_with_numpy_array),
        ("Image File Test", test_with_image_file),
        ("Performance Test", test_performance),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ {name} failed with exception: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 50)
    print("Test Summary")
    print("=" * 50)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠ {total - passed} test(s) failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
