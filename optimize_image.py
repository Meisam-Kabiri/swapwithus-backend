from PIL import Image
import io

def optimize_image(image_file, max_width=1200, quality=85):
      """
      Smart image optimization:
      - PNG with transparency → optimized PNG
      - PNG without transparency → JPEG (smaller)
      - JPEG → optimized JPEG
      - WebP → optimized WebP
      - Other formats → JPEG
      """
      img = Image.open(image_file)
      original_format = img.format

      # Resize if too large
      if img.width > max_width:
          ratio = max_width / img.width
          new_height = int(img.height * ratio)
          img = img.resize((max_width, new_height), Image.LANCZOS)

      output = io.BytesIO()

      # Decide output format based on image characteristics
      if original_format == 'PNG':
          # Check if PNG has transparency
          has_transparency = img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info)

          if has_transparency:
              # Keep as PNG to preserve transparency
              if img.mode == 'P':
                  img = img.convert('RGBA')
              img.save(output, format='PNG', optimize=True)
              output.seek(0)
              return output, 'image/png'
          else:
              # Convert to JPEG for smaller size
              if img.mode in ('RGBA', 'LA', 'P'):
                  img = img.convert('RGB')
              img.save(output, format='JPEG', quality=quality, optimize=True)
              output.seek(0)
              return output, 'image/jpeg'

      elif original_format == 'WEBP':
          # WebP is already efficient, keep it
          if img.mode in ('RGBA', 'LA'):
              # WebP supports transparency, keep it
              img.save(output, format='WEBP', quality=quality, optimize=True, lossless=False)
          else:
              img.save(output, format='WEBP', quality=quality, optimize=True)
          output.seek(0)
          return output, 'image/webp'

      else:
          # JPEG or other formats → convert to JPEG
          # Always convert to RGB for JPEG
          if img.mode != 'RGB':
              if img.mode in ('RGBA', 'LA'):
                  # Create white background for transparency
                  background = Image.new('RGB', img.size, (255, 255, 255))
                  background.paste(img, mask=img.split()[-1])
                  img = background
              elif img.mode == 'P':
                  img = img.convert('RGBA')
                  background = Image.new('RGB', img.size, (255, 255, 255))
                  background.paste(img, mask=img.split()[-1])
                  img = background
              else:
                  img = img.convert('RGB')

          img.save(output, format='JPEG', quality=quality, optimize=True)
          output.seek(0)
          return output, 'image/jpeg'


if __name__ == "__main__":
    file = "1.webp"
    output, type = optimize_image(file)
    with open("optimized_testimg.jpg", "wb") as f:
        f.write(output.read())
    